import json
from uuid import uuid4

from shapely import from_wkb
from shapely.geometry import MultiLineString

from app.repositories.base import Repository


class Game(Repository):
    def expire(self):
        return self.execute(
            "UPDATE territories SET active=false, lost_at=expires_at WHERE active AND expires_at<=now()"
        ).rowcount

    def existing_run(self, client_id):
        return self.one("SELECT user_id,result FROM runs WHERE client_run_id=:id", id=client_id)

    def recent_count(self, user_id):
        return self.execute(
            "SELECT count(*) FROM runs WHERE user_id=:id AND created_at>now()-interval '1 hour'",
            id=user_id,
        ).scalar_one()

    def insert_run(self, user_id, upload, verdict, result):
        segments = [s for s in verdict.segments if len(s) >= 2]
        track = MultiLineString(segments).wkt if segments else None
        report = {
            "version": 1,
            "status": verdict.status,
            "reasons": verdict.reasons,
            "dropped_point_count": verdict.dropped_point_count,
        }
        self.execute(
            """INSERT INTO runs(id,user_id,client_run_id,started_at,ended_at,duration_s,
            distance_m,avg_speed_ms,point_count,dropped_point_count,step_count,track,status,
            cheat_report,raw_upload,result) VALUES (:id,:uid,:cid,:start,:end,:duration,:distance,
            :speed,:count,:dropped,:steps,ST_GeomFromText(:track,4326),:status,
            CAST(:report AS jsonb),CAST(:raw AS jsonb),CAST(:result AS jsonb))""",
            id=result["id"],
            uid=user_id,
            cid=upload.client_run_id,
            start=upload.started_at,
            end=upload.ended_at,
            duration=verdict.duration_s,
            distance=verdict.distance_m,
            speed=verdict.distance_m / verdict.duration_s if verdict.duration_s else 0,
            count=len(verdict.points),
            dropped=verdict.dropped_point_count,
            steps=upload.step_count,
            track=track,
            status=verdict.status,
            report=json.dumps(report),
            raw=upload.model_dump_json(),
            result=json.dumps(result, default=str),
        )

    def finish_run(self, result):
        self.execute(
            """UPDATE runs SET result=CAST(:result AS jsonb),status=:status,
            fragment_count=:fragments,claimed_area_m2=:area,stolen_area_m2=:stolen WHERE id=:id""",
            id=result["id"],
            result=json.dumps(result, default=str),
            status=result["status"],
            fragments=result["fragment_count"],
            area=result["new_area_m2"],
            stolen=result["stolen_area_m2"],
        )

    def intersections(self, geometry, user_id):
        rows = self.all(
            """SELECT t.*,u.username,ST_AsBinary(t.geom) binary_geom
            FROM territories t JOIN users u ON u.id=t.owner_id
            WHERE t.active AND t.expires_at>now() AND ST_Intersects(t.geom,ST_GeomFromText(:wkt,4326))
            AND (t.owner_id=:uid OR t.owner_id IN (
                SELECT CASE WHEN requester_id=:uid THEN addressee_id ELSE requester_id END
                FROM accepted_friendships WHERE status='accepted' AND (requester_id=:uid OR addressee_id=:uid)))
            ORDER BY t.id FOR UPDATE OF t""",
            wkt=geometry.wkt,
            uid=user_id,
        )
        for row in rows:
            row["shape"] = from_wkb(bytes(row.pop("binary_geom")))
            row.pop("geom")
        return rows

    def create_contest(self, a, b):
        self.prune_contests()
        self.execute(
            """INSERT INTO contests(id,owner_a,owner_b,accepted_at,geom)
            SELECT :cid,least(CAST(:a AS uuid),CAST(:b AS uuid)),
                greatest(CAST(:a AS uuid),CAST(:b AS uuid)),
                (SELECT accepted_at FROM friendships WHERE
                    least(requester_id,addressee_id)=least(CAST(:a AS uuid),CAST(:b AS uuid))
                    AND greatest(requester_id,addressee_id)=greatest(CAST(:a AS uuid),CAST(:b AS uuid))),
                ST_Multi(ST_CollectionExtract(ST_UnaryUnion(ST_Collect(ST_Intersection(x.geom,y.geom))),3))
            FROM territories x JOIN territories y ON x.geom && y.geom
            WHERE x.owner_id=:a AND y.owner_id=:b AND x.active AND y.active
                AND x.expires_at>now() AND y.expires_at>now()
                AND ST_Area(ST_Intersection(x.geom,y.geom)::geography)>0.0001
            HAVING count(*)>0""",
            cid=uuid4(),
            a=a,
            b=b,
        )

    def prune_contests(self):
        # Expiry and captures by other friends remove only portions no longer jointly held.
        self.execute("""UPDATE contests c SET geom=coalesce((
            SELECT ST_Multi(ST_CollectionExtract(ST_UnaryUnion(ST_Collect(
                ST_Intersection(c.geom,ST_Multi(ST_CollectionExtract(ST_Intersection(a.geom,b.geom),3))))),3))
            FROM territories a JOIN territories b ON a.geom && b.geom
            WHERE a.owner_id=c.owner_a AND b.owner_id=c.owner_b
              AND a.active AND b.active AND a.expires_at>now() AND b.expires_at>now()
        ), ST_GeomFromText('MULTIPOLYGON EMPTY',4326))""")
        self.execute("DELETE FROM contests WHERE ST_IsEmpty(geom)")

    def contests(self, user_id):
        rows = self.all(
            """WITH visible AS (
            SELECT CAST(:id AS uuid) id UNION
            SELECT CASE WHEN requester_id=:id THEN addressee_id ELSE requester_id END
            FROM accepted_friendships WHERE status='accepted' AND (requester_id=:id OR addressee_id=:id)
        ) SELECT c.*,ST_AsBinary(c.geom) binary_geom FROM contests c
          WHERE c.owner_a IN (SELECT id FROM visible) AND c.owner_b IN (SELECT id FROM visible)
        """,
            id=user_id,
        )
        for row in rows:
            row["shape"] = from_wkb(bytes(row.pop("binary_geom")))
            row.pop("geom")
        return rows

    def renew_slice(self, row, overlap, won, expires, now, run_id):
        remaining = self.operation("ST_Difference", row["shape"], overlap)
        # Keep an audit snapshot when the old piece is wholly replaced.
        self.carve(row, remaining, None, now)
        regular = self.operation("ST_Difference", overlap, won)
        for shape, claimed in ((regular, row["claimed_at"]), (won, now)):
            if not shape.is_empty:
                self.add_territory(
                    row["owner_id"], run_id, shape, claimed, max(expires, row["expires_at"])
                )

    def operation(self, operation: str, a, b):
        if operation not in {"ST_Difference", "ST_Intersection"}:
            raise ValueError("Unsupported spatial operation")
        return from_wkb(
            bytes(
                self.execute(
                    f"""SELECT ST_AsBinary(ST_Multi(ST_CollectionExtract(
          {operation}(ST_GeomFromText(:a,4326),ST_GeomFromText(:b,4326)),3)))""",
                    a=a.wkt,
                    b=b.wkt,
                ).scalar_one()
            )
        )

    def area(self, geometry) -> float:
        if geometry.is_empty:
            return 0.0
        return float(
            self.execute(
                "SELECT ST_Area(ST_GeomFromText(:wkt,4326)::geography)", wkt=geometry.wkt
            ).scalar_one()
        )

    def carve(self, row, remaining, winner, now):
        if remaining.is_empty:
            # Keep the pre-loss geometry for the past-territory map and audit.
            self.execute(
                "UPDATE territories SET active=false,lost_at=:now,lost_to_id=:winner WHERE id=:id",
                now=now,
                winner=winner,
                id=row["id"],
            )
        else:
            self.execute(
                "UPDATE territories SET geom=ST_GeomFromText(:wkt,4326),area_m2=:area WHERE id=:id",
                wkt=remaining.wkt,
                area=self.area(remaining),
                id=row["id"],
            )

    def add_territory(self, user_id, run_id, geometry, now, expires):
        self.execute(
            """INSERT INTO territories(id,owner_id,run_id,geom,area_m2,claimed_at,expires_at)
          VALUES(:id,:uid,:rid,ST_GeomFromText(:wkt,4326),:area,:now,:expires)""",
            id=uuid4(),
            uid=user_id,
            rid=run_id,
            wkt=geometry.wkt,
            area=self.area(geometry),
            now=now,
            expires=expires,
        )

    def notify(self, victim, username, area, run_id):
        self.execute(
            """INSERT INTO notifications(id,user_id,kind,title,body,payload)
          VALUES(:id,:uid,'territory_stolen','Your territory changed hands',:body,CAST(:payload AS jsonb))""",
            id=uuid4(),
            uid=victim,
            body=f"{username} captured {area:.0f} m² of your territory.",
            payload=json.dumps({"run_id": str(run_id), "area_m2": area}),
        )

    def history(self, user_id, limit, offset):
        return [
            r["result"]
            for r in self.all(
                "SELECT result FROM runs WHERE user_id=:id ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
                id=user_id,
                limit=limit,
                offset=offset,
            )
        ]

    def territories(self, user_id, state):
        rows = self.all(
            """SELECT t.id,t.owner_id,u.username,t.area_m2,t.claimed_at,t.expires_at,
            ST_AsGeoJSON(t.geom)::json geometry FROM territories t JOIN users u ON u.id=t.owner_id
            WHERE ((:state='current' AND t.active AND t.expires_at>now())
                OR (:state='past' AND (NOT t.active OR t.expires_at<=now())))
              AND (t.owner_id=:id OR t.owner_id IN (
                SELECT CASE WHEN requester_id=:id THEN addressee_id ELSE requester_id END
                FROM accepted_friendships WHERE status='accepted' AND (requester_id=:id OR addressee_id=:id)))
            ORDER BY t.claimed_at DESC LIMIT 2000""",
            id=user_id,
            state=state,
        )
        contests = self.contests(user_id) if state == "current" else []
        for row in rows:
            ids = [c["id"] for c in contests if row["owner_id"] in (c["owner_a"], c["owner_b"])]
            row["contested_geometry"] = None
            if not ids:
                continue
            # Read-time expiry filtering avoids phantom contests if the worker is asleep.
            live = self.one(
                """SELECT ST_AsGeoJSON(ST_Multi(ST_CollectionExtract(
                ST_UnaryUnion(ST_Collect(ST_Intersection(c.geom,ST_Multi(ST_CollectionExtract(ST_Intersection(t.geom,o.geom),3))))),3)))::json geometry
                FROM territories t JOIN territories o ON t.geom && o.geom
                JOIN contests c ON (c.owner_a=t.owner_id AND c.owner_b=o.owner_id)
                                OR (c.owner_b=t.owner_id AND c.owner_a=o.owner_id)
                WHERE t.id=:tid AND o.active AND o.expires_at>now() AND c.id=ANY(:ids)
            """,
                tid=row["id"],
                ids=ids,
            )
            row["contested_geometry"] = live["geometry"]
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": str(r["id"]),
                    "geometry": r["geometry"],
                    "properties": {k: v for k, v in r.items() if k != "geometry"},
                }
                for r in rows
            ],
        }

    def stats(self, user_id):
        return self.one(
            """SELECT
          (SELECT coalesce(sum(area_m2),0) FROM territories WHERE owner_id=:id AND active AND expires_at>now()) area_m2,
          (SELECT count(*) FROM runs WHERE user_id=:id) run_count,
          (SELECT coalesce(sum(distance_m),0) FROM runs WHERE user_id=:id AND status<>'rejected') distance_m,
          (SELECT coalesce(sum(area_m2),0) FROM territories WHERE owner_id=:id AND active
              AND expires_at>now() AND expires_at<now()+interval '3 days') expiring_area_m2""",
            id=user_id,
        )

    def leaderboard(self, user_id):
        return self.all(
            """SELECT u.id,u.username,u.display_name,coalesce(sum(t.area_m2),0) area_m2
            FROM users u LEFT JOIN territories t ON t.owner_id=u.id AND t.active AND t.expires_at>now()
            WHERE u.id=:id OR u.id IN (SELECT CASE WHEN requester_id=:id THEN addressee_id ELSE requester_id END
                FROM accepted_friendships WHERE status='accepted' AND (requester_id=:id OR addressee_id=:id))
            GROUP BY u.id ORDER BY area_m2 DESC,u.username""",
            id=user_id,
        )

    def notifications(self, user_id, limit, offset):
        return self.all(
            "SELECT id,kind,title,body,payload,read_at,created_at FROM notifications WHERE user_id=:id ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
            id=user_id,
            limit=limit,
            offset=offset,
        )

    def unread(self, user_id):
        return self.execute(
            "SELECT count(*) FROM notifications WHERE user_id=:id AND read_at IS NULL", id=user_id
        ).scalar_one()

    def read_all(self, user_id):
        self.execute(
            "UPDATE notifications SET read_at=now() WHERE user_id=:id AND read_at IS NULL",
            id=user_id,
        )

    def register_device(self, user_id, data):
        self.execute(
            """INSERT INTO devices(id,user_id,apns_token,platform,app_version)
          VALUES (:id,:uid,:token,:platform,:version) ON CONFLICT(apns_token) DO UPDATE
          SET user_id=excluded.user_id,app_version=excluded.app_version,is_active=true""",
            id=uuid4(),
            uid=user_id,
            token=data.apns_token.lower(),
            platform=data.platform,
            version=data.app_version,
        )

    def unregister_device(self, user_id, token):
        self.execute(
            "UPDATE devices SET is_active=false WHERE user_id=:id AND apns_token=:token",
            id=user_id,
            token=token,
        )

    def health(self):
        return self.execute("SELECT PostGIS_Version()").scalar_one()

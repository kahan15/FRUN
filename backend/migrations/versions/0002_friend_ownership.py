"""Independent ownership and pairwise contested overlaps; preserves existing land."""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.execute("ALTER TABLE friendships ADD COLUMN accepted_at timestamptz")
    op.execute("UPDATE friendships SET accepted_at=created_at WHERE status='accepted'")
    op.execute("""CREATE TABLE contests (
        id uuid PRIMARY KEY, owner_a uuid NOT NULL REFERENCES users(id),
        owner_b uuid NOT NULL REFERENCES users(id), accepted_at timestamptz NOT NULL,
        geom geometry(MULTIPOLYGON,4326) NOT NULL,
        UNIQUE(owner_a,owner_b), CHECK(owner_a<owner_b), CHECK(ST_IsValid(geom))
    )""")
    op.execute("CREATE INDEX contests_geom ON contests USING gist(geom)")
    op.execute("""CREATE OR REPLACE FUNCTION assert_no_territory_overlap()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM territories a JOIN territories b ON a.id<>b.id
          AND a.geom && b.geom AND ST_Area(ST_Intersection(a.geom,b.geom)::geography)>0.0001
        WHERE a.id=NEW.id AND a.active AND b.active
          AND a.expires_at>clock_timestamp() AND b.expires_at>clock_timestamp()
          AND (a.owner_id=b.owner_id OR (EXISTS (
            SELECT 1 FROM friendships f WHERE f.status='accepted'
              AND least(f.requester_id,f.addressee_id)=least(a.owner_id,b.owner_id)
              AND greatest(f.requester_id,f.addressee_id)=greatest(a.owner_id,b.owner_id)
          ) AND NOT EXISTS (
            SELECT 1 FROM contests c WHERE c.owner_a=least(a.owner_id,b.owner_id)
              AND c.owner_b=greatest(a.owner_id,b.owner_id)
              AND ST_Area(ST_Difference(
                ST_Multi(ST_CollectionExtract(ST_Intersection(a.geom,b.geom),3)),c.geom)::geography)<=0.0001
          )))
      ) THEN RAISE EXCEPTION 'Unresolved ownership overlap outside a contest'
        USING ERRCODE='23514'; END IF;
      RETURN NULL;
    END $$""")


def downgrade():
    # Old global ownership cannot represent independent overlapping holdings. Never delete them.
    op.execute("""DO $$ BEGIN IF EXISTS (
        SELECT 1 FROM territories a JOIN territories b ON a.id<b.id
        AND a.geom && b.geom AND ST_Relate(a.geom,b.geom,'2********')
        WHERE a.active AND b.active
    ) THEN RAISE EXCEPTION 'Cannot downgrade while independent territories overlap';
    END IF; END $$""")
    op.execute("""CREATE OR REPLACE FUNCTION assert_no_territory_overlap()
    RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF EXISTS (SELECT 1 FROM territories a JOIN territories b ON a.id<>b.id
        AND a.geom && b.geom AND ST_Relate(a.geom,b.geom,'2********')
        WHERE a.id=NEW.id AND a.active AND b.active)
      THEN RAISE EXCEPTION 'Active territories overlap' USING ERRCODE='23514'; END IF;
      RETURN NULL;
    END $$""")
    op.execute("DROP TABLE contests")
    op.execute("ALTER TABLE friendships DROP COLUMN accepted_at")

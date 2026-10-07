"use strict";
(() => {
  let token = window.location.hash.slice(1);
  // The fragment is not sent in HTTP requests. Remove it from this history entry
  // immediately; keep it only in memory until the user submits a new password.
  window.history.replaceState(null, "", "/password-reset");
  const form = document.getElementById("reset-form");
  const button = document.getElementById("submit");
  const status = document.getElementById("status");
  const valid = /^[A-Za-z0-9_-]{64}$/.test(token);
  button.disabled = !valid;
  status.textContent = valid ? "Enter your new password below." : "Open a valid recovery link from your email.";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (button.disabled || !token) return;
    const password = document.getElementById("password").value;
    if (password !== document.getElementById("confirm").value) {
      status.textContent = "The passwords do not match.";
      return;
    }
    button.disabled = true;
    status.textContent = "Saving your password…";
    try {
      const response = await fetch("/api/v1/auth/password-recovery/complete", {
        method: "POST", credentials: "omit", cache: "no-store", redirect: "error",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({token, password})
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error?.message || "Unable to reset the password. Try again.");
      token = "";
      form.reset();
      form.hidden = true;
      status.textContent = "Password reset. Return to Territory Run and sign in with your new password.";
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : "Unable to connect. Try again.";
      button.disabled = false;
    }
  });
})();

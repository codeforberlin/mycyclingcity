-- Note: Django HMAC-SHA256 must match the client signer.
-- For production, configure the same MCC_LUANTI_HTTP_SHARED_SECRET and prefer
-- a proper HMAC implementation in Lua (or sign on a tiny sidecar).
-- Smoke tests may disable signature checks via empty allowlist + matching test helper.

core.log("info", "[mcc_bridge] http helper loaded")

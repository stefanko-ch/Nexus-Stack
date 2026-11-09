// =============================================================================
// Node-RED settings for Nexus-Stack
// =============================================================================
// Loaded with --settings from the stack directory (docker-compose.yml).
// Only what differs from Node-RED's defaults is set here.
//
// The editor has no login by default. adminAuth turns it on, with one
// user, nexus-admin, whose password comes from NODE_RED_ADMIN_PASSWORD
// (Infisical folder `node-red`). Node-RED wants a bcrypt hash; it is made
// here at start from the plain value, with the bcryptjs Node-RED ships.
// =============================================================================

const bcrypt = require("/usr/src/node-red/node_modules/bcryptjs");

const password = process.env.NODE_RED_ADMIN_PASSWORD;
if (!password) {
  // Starting without it would leave the editor, which runs arbitrary code,
  // without a login.
  throw new Error("NODE_RED_ADMIN_PASSWORD is not set");
}

module.exports = {
  uiPort: 1880,
  flowFile: "flows.json",
  // Encrypts credentials stored in flows (flows_cred.json).
  credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET,
  adminAuth: {
    type: "credentials",
    users: [
      {
        username: "nexus-admin",
        password: bcrypt.hashSync(password, 10),
        permissions: "*",
      },
    ],
  },
  // No usage diagnostics and no update check against nodered.org.
  diagnostics: { enabled: false, ui: false },
  telemetry: { enabled: false, updateNotification: false },
  logging: { console: { level: "info", metrics: false, audit: false } },
};

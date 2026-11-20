// Copy to config.js and fill in. config.js is git-ignored.
// Locally: other-scripts/write_frontend_config.sh writes it from .env.
// In CodePipeline (P2): written at build time from SSM Parameter Store.
window.APP_CONFIG = {
  apiKey: "YOUR_API_GATEWAY_KEY"
};

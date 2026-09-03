/** Dev defaults. `appToken` matches the backend's .env.example APP_TOKEN so a
 *  local `ng serve` works out of the box; production overrides it below and
 *  no real token is ever committed here. */
export const environment = {
  production: false,
  appToken: 'dev-local-token',
};

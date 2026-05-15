export function getAppConfig() {
  return window.APP_CONFIG || {};
}

export function getConfig(key, defaultValue = null) {
  const config = getAppConfig();
  return key in config ? config[key] : defaultValue;
}

export function hasConfig(key) {
  const config = getAppConfig();
  return key in config;
}
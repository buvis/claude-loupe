function readSettingsSafely(path) {
  try {
    return load(path);
  } catch (err) {
    console.error("settings unreadable", err);
    throw err;
  }
}

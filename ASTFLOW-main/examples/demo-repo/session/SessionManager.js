/** Demo session lifecycle extracted from AuthService in v2. */
export class SessionManager {
  constructor() { this.savedSession = null; }
  create(identity) {
    this.savedSession = { username: identity.username, expiresAt: Date.now() + 3600000 };
    return this.savedSession;
  }
  /** Restore a saved session. Expired sessions require the user to sign in again. */
  restore() {
    if (!this.savedSession || this.savedSession.expiresAt <= Date.now()) return null;
    return this.savedSession;
  }
  clear() { this.savedSession = null; }
}

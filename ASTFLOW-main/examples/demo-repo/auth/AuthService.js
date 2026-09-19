import { validateCredentials } from './credentials.js';
import { SessionManager } from '../session/SessionManager.js';

export class AuthService {
  constructor() { this.sessions = new SessionManager(); }
  /** Validate credentials and create an authenticated session. */
  login(credentials) {
    const identity = validateCredentials(credentials);
    return this.sessions.create(identity);
  }
  /** Delegate session restoration to the extracted lifecycle component. */
  restore() { return this.sessions.restore(); }
}

import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { SessionManager } from '../session/SessionManager.js';

test('expired sessions require the user to sign in again', () => {
  const sessions = new SessionManager();
  sessions.savedSession = { username: 'demo', expiresAt: 0 };
  assert.equal(sessions.restore(), null);
});

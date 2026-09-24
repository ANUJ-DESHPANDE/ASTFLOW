/** Reject a login missing username or token. Demo validation, not authentication. */
export function validateCredentials(credentials) {
  if (!credentials?.username || !credentials?.token) throw new Error('Missing username or token');
  return { username: credentials.username };
}

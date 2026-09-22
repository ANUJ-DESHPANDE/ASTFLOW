export async function request<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { signal: AbortSignal.timeout(90_000), ...(body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }) });
  } catch (error) {
    throw new Error((error as Error).name === 'TimeoutError' ? 'The request timed out. Check the backend and try again.' : 'Cannot reach ASTFLOW. Check that the local backend is running.');
  }
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`ASTFLOW returned an invalid response (HTTP ${response.status}). Check the backend logs.`); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : response.status === 422 ? 'Some request values are invalid. Check your input.' : `Request failed (HTTP ${response.status}).`);
  return data as T;
}

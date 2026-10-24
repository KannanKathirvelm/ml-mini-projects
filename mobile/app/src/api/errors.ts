export class ApiError extends Error {
  constructor(message: string, public status: number | null, public kind: 'http' | 'network' | 'timeout' | 'parse') {
    super(message);
  }
}

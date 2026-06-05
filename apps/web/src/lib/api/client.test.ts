import { describe, it, expect } from 'vitest';
import { ApiError, formatApiError, readApiData, localAuthHeaders } from './client';

describe('client api utilities', () => {
  it('localAuthHeaders returns correct headers', () => {
    const headers = localAuthHeaders('test-workspace-id', 'admin');
    expect(headers['x-user-id']).toBe('00000000-0000-0000-0000-000000000001');
    expect(headers['x-test-workspaces']).toBe('test-workspace-id:admin');
  });

  it('readApiData parses successful response', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ success: true, data: { foo: 'bar' } })
    } as unknown as Response;
    const result = await readApiData(mockResponse, 'Fallback');
    expect(result).toEqual({ foo: 'bar' });
  });

  it('readApiData throws on error response', async () => {
    const mockResponse = {
      ok: false,
      status: 400,
      url: 'http://localhost/test',
      json: async () => ({ success: false, error: { message: 'Invalid data' } })
    } as unknown as Response;
    
    await expect(readApiData(mockResponse, 'Fallback'))
      .rejects.toThrow('Invalid data');
    await expect(readApiData(mockResponse, 'Fallback'))
      .rejects.toBeInstanceOf(ApiError);
  });

  it('readApiData throws fallback on parse failure', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      url: 'http://localhost/test',
      json: async () => { throw new Error('Syntax error'); }
    } as unknown as Response;
    
    await expect(readApiData(mockResponse, 'Fallback'))
      .rejects.toThrow('Fallback');
  });

  it('formatApiError turns browser fetch failures into professional connection copy', () => {
    const message = formatApiError(new TypeError('Failed to fetch'), 'Fallback');

    expect(message).toContain('Unable to reach the API server');
    expect(message).toContain('Failed to fetch');
  });
});

import { getErrorMessage } from '../apiError';

describe('getErrorMessage', () => {
  it('returns a string API detail', () => {
    const error = { response: { data: { detail: 'Not allowed' } } };

    expect(getErrorMessage(error, 'Fallback')).toBe('Not allowed');
  });

  it('formats FastAPI validation details as renderable text', () => {
    const error = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'title'], msg: 'Field required', type: 'missing' },
            { loc: ['body', 'content'], msg: 'Field required', type: 'missing' },
          ],
        },
      },
    };

    expect(getErrorMessage(error, 'Fallback')).toBe(
      'title: Field required, content: Field required'
    );
  });

  it('uses the fallback for unknown error shapes', () => {
    expect(getErrorMessage(new Error('Network failed'), 'Try again')).toBe('Try again');
  });
});

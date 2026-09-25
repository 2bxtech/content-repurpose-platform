interface FastApiValidationError {
  loc?: Array<string | number>;
  msg?: string;
}

interface ApiErrorShape {
  response?: {
    data?: {
      detail?: unknown;
    };
  };
}

const isValidationError = (value: unknown): value is FastApiValidationError =>
  typeof value === 'object' && value !== null && 'msg' in value;

export const getErrorMessage = (error: unknown, fallback: string): string => {
  const detail = (error as ApiErrorShape)?.response?.data?.detail;

  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .filter(isValidationError)
      .map((item) => {
        const location = item.loc
          ?.filter((part) => part !== 'body')
          .map(String)
          .join('.');
        const message = typeof item.msg === 'string' ? item.msg : '';
        return location && message ? `${location}: ${message}` : message;
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join(', ');
    }
  }

  return fallback;
};

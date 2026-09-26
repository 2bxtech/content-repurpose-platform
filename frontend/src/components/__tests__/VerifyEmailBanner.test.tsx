import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import VerifyEmailBanner from '../VerifyEmailBanner';
import { useAuth } from '../../context/AuthContext';
import { resendVerification } from '../../services/authService';

jest.mock('../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../services/authService', () => ({ resendVerification: jest.fn() }));

const mockUseAuth = useAuth as jest.Mock;
const mockResend = resendVerification as jest.Mock;

const user = (is_verified: boolean) => ({
  user: { id: 'u1', email: 'a@example.com', username: 'a', is_active: true, is_verified },
});

describe('VerifyEmailBanner', () => {
  it('asks unverified users to confirm and can resend the link', async () => {
    mockUseAuth.mockReturnValue(user(false));
    mockResend.mockResolvedValue({ sent: true });

    render(<VerifyEmailBanner />);
    expect(screen.getByText(/confirm your email address/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /resend email/i }));
    await waitFor(() => expect(screen.getByText(/sent a new confirmation link/i)).toBeInTheDocument());
    expect(mockResend).toHaveBeenCalledTimes(1);
  });

  it('renders nothing for verified or signed-out users', () => {
    mockUseAuth.mockReturnValue(user(true));
    const { container, rerender } = render(<VerifyEmailBanner />);
    expect(container).toBeEmptyDOMElement();

    mockUseAuth.mockReturnValue({ user: null });
    rerender(<VerifyEmailBanner />);
    expect(container).toBeEmptyDOMElement();
  });
});

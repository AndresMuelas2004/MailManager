import { Navigate } from 'react-router-dom';

import { useAuth } from '../../../app/providers/AuthContext';
import useGoogleLogin from '../hooks/useGoogleLogin';
import LoginBranding from '../components/LoginBranding';
import GoogleSignInButton from '../components/GoogleSignInButton';

export default function LoginPage() {
  const { user, loading: authLoading } = useAuth();
  const { buttonRef, error, loading } = useGoogleLogin();

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  if (user) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="flex min-h-screen">
      <LoginBranding />
      <GoogleSignInButton buttonRef={buttonRef} error={error} loading={loading} />
    </div>
  );
}

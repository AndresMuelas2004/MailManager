import AuthProvider from './AuthProvider';
import QueryProvider from './QueryProvider';
import AppRouter from '../routes/router';

export default function Providers() {
  return (
    <QueryProvider>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
    </QueryProvider>
  );
}

import AuthProvider from "./AuthProvider";
import AppRouter from "../routes/router";

export default function Providers() {
  return (
    <AuthProvider>
      <AppRouter />
    </AuthProvider>
  );
}

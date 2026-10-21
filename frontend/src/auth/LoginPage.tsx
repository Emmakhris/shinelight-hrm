import Business from "@mui/icons-material/Business";
import LockOutlined from "@mui/icons-material/LockOutlined";
import { Alert, Box, Button, Card, CardContent, Divider, Link, Stack, TextField, Typography } from "@mui/material";
import axios from "axios";
import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { useAuth, type Me } from "./AuthContext";

type Step = "login" | "mfa" | "setup" | "forgot" | "reset" | "sso";

const SSO_ERRORS: Record<string, string> = {
  cancelled: "Single sign-on was cancelled.",
  expired: "The single sign-on attempt expired. Please try again.",
  state_mismatch: "The sign-in response didn't match this browser. Please try again.",
  no_account: "There is no ShineLight HRM account for your work email. Please contact HR.",
  domain_not_allowed: "Your email domain isn't set up for single sign-on here.",
  email_unverified: "Your identity provider hasn't verified your email address.",
  inactive: "Your account is disabled. Please contact HR.",
  locked: "Your account is temporarily locked. Try again later.",
};

export default function LoginPage() {
  const { setMe } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [step, setStep] = useState<Step>(params.get("uid") ? "reset" : "login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [mfaToken, setMfaToken] = useState("");
  const [methods, setMethods] = useState<string[]>([]);
  const [method, setMethod] = useState("totp");
  const [qr, setQr] = useState<string | null>(null);
  const ssoError = params.get("sso_error");
  const [error, setError] = useState<string | null>(
    ssoError ? SSO_ERRORS[ssoError] || "Single sign-on failed. Please try again or contact your IT administrator." : null);
  const [email, setEmail] = useState("");
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const done = (me: Me) => {
    setMe(me);
    nav(me.must_change_password ? "/change-password" : "/", { replace: true });
  };

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const submitLogin = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      let data;
      try {
        data = (await api.post("/auth/login/", { username, password })).data;
      } catch (err) {
        if (axios.isAxiosError(err) && err.response?.data?.code === "sso_required") {
          setEmail(username.includes("@") ? username : "");
          setStep("sso");
        }
        throw err;
      }
      if (data.mfa_required) {
        setMfaToken(data.mfa_token);
        setMethods(data.mfa_methods);
        if (!data.mfa_methods.length || data.mfa_setup_required) {
          const setup = await api.post("/auth/mfa/setup/", { mfa_token: data.mfa_token });
          setQr(setup.data.qr_svg);
          setStep("setup");
        } else {
          setMethod(data.mfa_methods[0]);
          if (data.mfa_methods[0] === "sms") await api.post("/auth/mfa/sms/", { mfa_token: data.mfa_token });
          setStep("mfa");
        }
        return;
      }
      done(data);
    });
  };

  const submitCode = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const { data } = await api.post("/auth/mfa/verify/", { mfa_token: mfaToken, code, method });
      done(data);
    });
  };

  const sendSms = () => run(async () => {
    setMethod("sms");
    await api.post("/auth/mfa/sms/", { mfa_token: mfaToken });
    setInfo("A code has been sent to your registered phone.");
  });

  const startTotpSetup = () => run(async () => {
    const setup = await api.post("/auth/mfa/setup/", { mfa_token: mfaToken });
    setQr(setup.data.qr_svg);
    setMethod("totp");
    setStep("setup");
  });

  const submitSso = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const { data } = await api.post("/sso/discover/", { email });
      window.location.assign(`${data.start_url}?next=${encodeURIComponent("/")}`);
    });
  };

  const submitForgot = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const { data } = await api.post("/auth/password-reset/", { email: username });
      setInfo(data.detail);
    });
  };

  const submitReset = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const { data } = await api.post("/auth/password-reset/confirm/", {
        uid: params.get("uid"), token: params.get("token"), new_password: password,
      });
      setInfo(data.detail);
      setStep("login");
      setPassword("");
    });
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center", p: 2,
      background: "linear-gradient(135deg, #0f3d5e 0%, #155e75 60%, #f5b700 160%)" }}>
      <Card variant="elevation" sx={{ width: "100%", maxWidth: 420, borderRadius: 3 }} elevation={8}>
        <CardContent sx={{ p: 4 }}>
          <Stack alignItems="center" spacing={1} mb={3}>
            <Box component="img" src="/favicon.svg" alt="" sx={{ width: 56, height: 56 }} />
            <Typography variant="h5" fontWeight={700}>ShineLight HRM</Typography>
            <Typography variant="body2" color="text.secondary">
              {step === "login" && "Sign in to your account"}
              {step === "mfa" && "Two-step verification"}
              {step === "setup" && "Set up your authenticator app"}
              {step === "forgot" && "Reset your password"}
              {step === "reset" && "Choose a new password"}
              {step === "sso" && "Sign in with your organization account"}
            </Typography>
          </Stack>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          {info && <Alert severity="info" sx={{ mb: 2 }}>{info}</Alert>}

          {step === "login" && (
            <form onSubmit={submitLogin}>
              <Stack spacing={2}>
                <TextField label="Username or email" value={username} onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username" autoFocus required fullWidth />
                <TextField label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password" required fullWidth />
                <Button type="submit" variant="contained" size="large" disabled={busy} startIcon={<LockOutlined />}>
                  Sign in
                </Button>
                <Link component="button" type="button" variant="body2" onClick={() => { setStep("forgot"); setInfo(null); }}>
                  Forgot password?
                </Link>
                <Divider>or</Divider>
                <Button variant="outlined" startIcon={<Business />} onClick={() => { setStep("sso"); setError(null); }}>
                  Sign in with single sign-on
                </Button>
              </Stack>
            </form>
          )}

          {step === "sso" && (
            <form onSubmit={submitSso}>
              <Stack spacing={2}>
                <Typography variant="body2">Enter your work email and you'll be sent to your organization's sign-in page (for example Microsoft 365).</Typography>
                <TextField label="Work email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus required />
                <Button type="submit" variant="contained" size="large" disabled={busy}>Continue</Button>
                <Link component="button" type="button" variant="body2" onClick={() => { setStep("login"); setError(null); }}>Sign in with a password instead</Link>
              </Stack>
            </form>
          )}

          {(step === "mfa" || step === "setup") && (
            <form onSubmit={submitCode}>
              <Stack spacing={2}>
                {step === "setup" && qr && (
                  <>
                    <Typography variant="body2">
                      Your role requires two-step verification. Scan this code with Google Authenticator, Microsoft
                      Authenticator or a similar app, then enter the 6-digit code.
                    </Typography>
                    <Box component="img" src={qr} alt="Authenticator QR code" sx={{ width: 200, mx: "auto", bgcolor: "#fff", p: 1 }} />
                  </>
                )}
                {step === "mfa" && (
                  <Typography variant="body2">
                    {method === "sms" ? "Enter the code sent to your phone." : "Enter the 6-digit code from your authenticator app."}
                  </Typography>
                )}
                <TextField label="Verification code" value={code} onChange={(e) => setCode(e.target.value)}
                  inputProps={{ inputMode: "numeric", maxLength: 6, autoComplete: "one-time-code" }} autoFocus required />
                <Button type="submit" variant="contained" size="large" disabled={busy}>Verify</Button>
                {step === "mfa" && methods.includes("sms") && method !== "sms" && (
                  <Link component="button" type="button" variant="body2" onClick={sendSms}>Send a code by SMS instead</Link>
                )}
                {step === "mfa" && !methods.includes("totp") && (
                  <Link component="button" type="button" variant="body2" onClick={startTotpSetup}>Set up an authenticator app</Link>
                )}
              </Stack>
            </form>
          )}

          {step === "forgot" && (
            <form onSubmit={submitForgot}>
              <Stack spacing={2}>
                <TextField label="Work email" type="email" value={username} onChange={(e) => setUsername(e.target.value)} required />
                <Button type="submit" variant="contained" disabled={busy}>Send reset link</Button>
                <Link component="button" type="button" variant="body2" onClick={() => setStep("login")}>Back to sign in</Link>
              </Stack>
            </form>
          )}

          {step === "reset" && (
            <form onSubmit={submitReset}>
              <Stack spacing={2}>
                <TextField label="New password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  helperText="At least 10 characters; avoid common words." required autoComplete="new-password" />
                <Button type="submit" variant="contained" disabled={busy}>Set password</Button>
              </Stack>
            </form>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}

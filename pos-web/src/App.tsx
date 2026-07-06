import { useState } from "react";
import { api } from "./api/client";

function App() {
  const [email, setEmail] = useState("owner001@example.com");
  const [password, setPassword] = useState("12345678");
  const [message, setMessage] = useState("");

  async function login() {
    try {
      const res = await api.post("/auth/login", { email, password });
      localStorage.setItem("token", res.data.token);
      setMessage("Login successful");
    } catch (e: any) {
      setMessage(e.response?.data?.detail || "Login failed");
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#f3f4f6" }}>
      <div style={{ width: 380, background: "white", padding: 30, borderRadius: 18, boxShadow: "0 10px 30px #0002" }}>
        <h1 style={{ fontSize: 30, fontWeight: 800 }}>ApexRetail POS</h1>
        <p>Welcome back</p>

        <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Email"
          style={{ width: "100%", padding: 12, marginTop: 20 }} />

        <input value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" type="password"
          style={{ width: "100%", padding: 12, marginTop: 12 }} />

        <button onClick={login} style={{ width: "100%", padding: 14, marginTop: 20 }}>
          Login
        </button>

        <p>{message}</p>
      </div>
    </div>
  );
}

export default App;

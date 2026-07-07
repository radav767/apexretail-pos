import { useState } from "react";
import { api } from "./api/client";

type Screen = "login" | "register" | "dashboard";

function App() {
  const [screen, setScreen] = useState<Screen>(
    localStorage.getItem("token") ? "dashboard" : "login"
  );

  const [email, setEmail] = useState("owner001@example.com");
  const [password, setPassword] = useState("12345678");
  const [message, setMessage] = useState("");

  const [businessName, setBusinessName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [phone, setPhone] = useState("");
  const [country, setCountry] = useState("Zimbabwe");
  const [businessType, setBusinessType] = useState("Retail");
  const [confirmPassword, setConfirmPassword] = useState("");

  async function login() {
    try {
      const res = await api.post("/auth/login", { email, password });
      localStorage.setItem("token", res.data.token);
      localStorage.setItem("user", JSON.stringify(res.data.user || {}));
      setMessage("");
      setScreen("dashboard");
    } catch (e: any) {
      setMessage(e.response?.data?.detail || "Login failed");
    }
  }

  async function register() {
    try {
      const res = await api.post("/auth/register", {
        email,
        password,
        confirm_password: confirmPassword,
        business_name: businessName,
        owner_name: ownerName,
        business_type: businessType,
        country,
        phone,
      });

      if (res.data.token) {
        localStorage.setItem("token", res.data.token);
        localStorage.setItem("user", JSON.stringify(res.data.user || {}));
        setScreen("dashboard");
      } else {
        setScreen("login");
      }
      setMessage("");
    } catch (e: any) {
      setMessage(e.response?.data?.detail || "Registration failed");
    }
  }

  function logout() {
    localStorage.clear();
    setScreen("login");
  }

  if (screen === "dashboard") {
    return (
      <div style={{ minHeight: "100vh", background: "#f3f4f6", padding: 40 }}>
        <h1 style={{ fontSize: 36, fontWeight: 900 }}>ApexRetail POS Dashboard</h1>
        <p>Business setup successful.</p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 18, marginTop: 30 }}>
          {["Sales", "Products", "Inventory", "Customers", "Reports", "Employees", "Settings", "Backoffice"].map(item => (
            <div key={item} style={{ background: "white", padding: 30, borderRadius: 16, boxShadow: "0 8px 20px #0001" }}>
              <h2>{item}</h2>
              <p>Module ready</p>
            </div>
          ))}
        </div>

        <button onClick={logout} style={{ marginTop: 30, padding: 14, width: 180 }}>
          Logout
        </button>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#f3f4f6" }}>
      <div style={{ width: 460, background: "white", padding: 34, borderRadius: 20, boxShadow: "0 10px 30px #0002" }}>
        <h1 style={{ textAlign: "center", fontSize: 32, fontWeight: 900 }}>ApexRetail POS</h1>

        <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
          <button onClick={() => setScreen("login")} style={{ flex: 1, padding: 12 }}>Login</button>
          <button onClick={() => setScreen("register")} style={{ flex: 1, padding: 12 }}>Register</button>
        </div>

        {screen === "register" && (
          <>
            <input placeholder="Business Name" value={businessName} onChange={e => setBusinessName(e.target.value)} style={input} />
            <input placeholder="Owner Name" value={ownerName} onChange={e => setOwnerName(e.target.value)} style={input} />
            <input placeholder="Phone" value={phone} onChange={e => setPhone(e.target.value)} style={input} />
            <input placeholder="Country" value={country} onChange={e => setCountry(e.target.value)} style={input} />
            <input placeholder="Business Type" value={businessType} onChange={e => setBusinessType(e.target.value)} style={input} />
          </>
        )}

        <input placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} style={input} />
        <input placeholder="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} style={input} />

        {screen === "register" && (
          <input placeholder="Confirm Password" type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} style={input} />
        )}

        <button onClick={screen === "login" ? login : register} style={{ width: "100%", padding: 15, marginTop: 20 }}>
          {screen === "login" ? "Login" : "Create Business"}
        </button>

        <p style={{ textAlign: "center", color: "crimson" }}>{message}</p>
      </div>
    </div>
  );
}

const input = {
  width: "100%",
  padding: 13,
  marginTop: 12,
  boxSizing: "border-box" as const,
};

export default App;

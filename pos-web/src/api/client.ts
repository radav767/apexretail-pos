import axios from "axios";

export const api = axios.create({
  baseURL: "https://api.apexpos.cloud/api",
  headers: { "Content-Type": "application/json" },
});

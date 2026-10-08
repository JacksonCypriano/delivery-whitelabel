import { hydrateRoot } from "react-dom/client";
import { PublicApp } from "./PublicApp";
import "./public.css";
const root = document.getElementById("public-root");
const data = document.getElementById("public-data");
if (root && data) hydrateRoot(root, <PublicApp data={JSON.parse(data.textContent || "{}")} />);

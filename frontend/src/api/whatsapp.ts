import { request, post, formData } from "./client";
export const whatsapp = {
  get: (query = "") => request("whatsapp/" + query),
  status: () => request("whatsapp/?format=status"),
  action: (action: string) => post("whatsapp/", formData({ action })),
};

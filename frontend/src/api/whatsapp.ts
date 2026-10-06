import { request, post, formData } from "./client";
export const whatsapp = {
  get: () => request("whatsapp/"),
  status: () => request("whatsapp/?format=status"),
  action: (action: string) => post("whatsapp/", formData({ action })),
};

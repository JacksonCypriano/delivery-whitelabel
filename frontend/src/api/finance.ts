import { request, post } from "./client";
export const finance = {
  get: (path = "") => request("finance/" + path),
  post: (path: string, data = new FormData()) => post("finance/" + path, data),
};

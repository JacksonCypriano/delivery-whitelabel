import { request, post, formData } from "./client";
export const resources = {
  selectAll: (key: string, query: string) =>
    post(`resources/${key}/selection/?${query}`, new FormData()),
  list: (key: string, query: string) => request(`resources/${key}/${query}`),
  detail: (key: string, id: string) =>
    request(`resources/${key}/${id === "novo" ? "new" : id}/`),
  save: (key: string, id: string, data: FormData) =>
    post(`resources/${key}/${id === "novo" ? "new" : id}/`, data),
  remove: (key: string, id: string, confirmed = false) =>
    request(`resources/${key}/${id}/${confirmed ? "?confirm=yes" : ""}`, {
      method: "DELETE",
    }),
  action: (
    key: string,
    action: string,
    ids: string[],
    confirmed = false,
    selection = "",
  ) =>
    post(
      `resources/${key}/actions/`,
      formData({ action, ids, selection, confirmed: confirmed ? "yes" : "no" }),
    ),
};

import { describe, expect, it } from "vitest";
import { actionLabel, itemDetails, money } from "./orderHelpers";

describe("order helpers", () => {
  it("formats money for the operational panel", () => {
    expect(money("12.5")).toContain("12,50");
  });

  it("exposes labels for the new operational transitions", () => {
    expect(actionLabel.preparing).toBe("Iniciar preparo");
    expect(actionLabel.out_for_delivery).toBe("Saiu para entrega");
    expect(actionLabel.delivered).toBe("Marcar entregue");
  });

  it("renders customization snapshots without depending on current catalog", () => {
    const lines = itemDetails({
      customizations: [
        { group_name: "Adicionais", option_name: "Bacon" },
      ],
    });
    expect(lines.join(" ")).toContain("Bacon");
  });
});

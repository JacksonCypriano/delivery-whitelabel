import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Marketplace } from "./Marketplace";
import { Catalog } from "./Commerce";

const store = {
  name: "Bella Massa", slug: "vitrine-demo", logo: "/media/logo.png", banner: "/media/banner.png",
  is_open: true, accepts_pickup: true, accepts_delivery: true, pickup_address: "Rua de Teste, 123",
  cart_count: 0, hours: [], brand: { primary_color: "#A82832", show_product_image: true, show_search_bar: true },
};

describe("paridade visual do frontend público React", () => {
  it("restaura hero, filtros e cartões do marketplace", () => {
    const html = renderToStaticMarkup(<Marketplace data={{
      csrf: "csrf-test", user: { authenticated: false },
      props: {
        search: "", selected_city: "", selected_state: "", selected_category: "", cities: [],
        open_only: false, favorites_only: false, location_active: false, global_delivery_location: null,
        customer_addresses: [], favorite_count: 0, result_count: 1, categories: [],
        stores: [{ id: 1, name: "Bella Massa", url: "https://vitrine-demo.hml.vemdedelivery.com.br/",
          logo_url: "/media/logo.png", city: "Itapevi", state: "SP", description: "Loja demo",
          is_open: true, delivery: { status: "pickup_only" }, is_favorite: false,
          matched_products: [], categories: [] }],
        pagination: { page: 1, previous: null, next: null },
      },
    }} />);
    expect(html).toContain("Deu vontade?");
    expect(html).toContain("mp-hero-panel");
    expect(html).toContain("mp-store-card");
    expect(html).toContain("Bella Massa");
    expect(html).toContain("Ver cardápio");
  });

  it("restaura banner, identidade, categorias e cartões sem perder a seleção React", () => {
    const html = renderToStaticMarkup(<Catalog data={{
      csrf: "csrf-test", store,
      props: { categories: [{ id: 1, name: "Pizzas", products: [{ id: 20,
        slug: "margherita", name: "Pizza Margherita", description: "Massa artesanal",
        price: "49.90", original_price: "49.90", sale_price: null, is_featured: false,
        is_vegan: false, is_spicy: false, available: true, prep_time: 30,
        weight: "", calories: null, image: "/media/pizza.jpg", images: [], min_qty: 1, max_qty: 5,
      }] }], delivery_zones: [], open_product_slug: "", deep_link_unavailable: false },
    }} />);
    expect(html).toContain("catalog-banner-v2");
    expect(html).toContain("catalog-identity-v2");
    expect(html).toContain("catalog-product-card-v2");
    expect(html).toContain("Pizza Margherita");
    expect(html).toContain("Buscar no cardápio");
    expect(html).toContain("/checkout/cart/");
  });
});

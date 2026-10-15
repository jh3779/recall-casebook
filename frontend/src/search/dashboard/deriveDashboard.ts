import { hasCauseText, type Card, type SearchResponse } from "../types";

export interface CountRow { label: string; count: number }
export interface SupplierSignal { name: string; campnos: string[]; components: string[] }

export interface DashboardData {
  cards: Card[];
  total: number;
  customerCount: number;
  otherCount: number;
  cause: { filled: number; stated: number; missing: number };
  investigationCards: number;
  investigationActions: number;
  part573Cards: number;
  productionCards: number;
  duplicateGroups: number;
  components: CountRow[];
  years: CountRow[];
  suppliers: SupplierSignal[];
}

const countByCampaign = (cards: Card[], values: (card: Card) => string[]) => {
  const groups = new Map<string, Set<string>>();
  for (const card of cards) {
    for (const value of new Set(values(card).filter(Boolean))) {
      const campaigns = groups.get(value) ?? new Set<string>();
      campaigns.add(card.campno);
      groups.set(value, campaigns);
    }
  }
  return [...groups].map(([label, campaigns]) => ({ label, count: campaigns.size }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
};

export function deriveDashboard(response: SearchResponse): DashboardData {
  const cards = [...response.customer_precedents, ...response.precedents];
  const filled = cards.filter((card) => card.cause.status === "filled").length;
  const stated = cards.filter((card) => card.cause.status === "stated_unknown").length;
  const actionSet = new Set(cards.flatMap((card) => card.investigations.map((item) => item.action)));
  const supplierMap = new Map<string, { campnos: Set<string>; components: Set<string> }>();
  for (const card of cards) {
    const supplier = card.checklist.find((item) => item.item === "supplier");
    for (const evidence of supplier?.evidence ?? []) {
      const group = supplierMap.get(evidence.text) ?? { campnos: new Set(), components: new Set() };
      group.campnos.add(card.campno);
      card.components.forEach((component) => group.components.add(component));
      supplierMap.set(evidence.text, group);
    }
  }
  return {
    cards,
    total: cards.length,
    customerCount: response.customer_precedents.length,
    otherCount: response.precedents.length,
    cause: { filled, stated, missing: cards.length - filled - stated },
    investigationCards: cards.filter((card) => card.investigations.length).length,
    investigationActions: actionSet.size,
    part573Cards: cards.filter((card) => hasCauseText(card.cause)
      || card.checklist.some((item) => item.item === "production_period" || item.item === "supplier")).length,
    productionCards: cards.filter((card) => card.checklist.some((item) => item.item === "production_period")).length,
    duplicateGroups: new Set(cards.map((card) => card.dup_group)).size,
    components: countByCampaign(cards, (card) => card.components).slice(0, 7),
    years: countByCampaign(cards, (card) => [/^\d{4}/.exec(card.received_date)?.[0] ?? "날짜 미상"])
      .sort((a, b) => a.label.localeCompare(b.label)),
    suppliers: [...supplierMap].map(([name, value]) => ({
      name,
      campnos: [...value.campnos].sort(),
      components: [...value.components].sort(),
    })).sort((a, b) => b.campnos.length - a.campnos.length || a.name.localeCompare(b.name)),
  };
}

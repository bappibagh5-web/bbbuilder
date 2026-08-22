import type { BidPackage } from "@/types";
const requirements = [
  "Provide lump-sum pricing.",
  "Identify all taxes separately where applicable.",
  "Clearly identify exclusions.",
  "Identify allowances and alternates.",
  "Confirm labour and material are included.",
  "Provide estimated duration.",
  "Confirm permit responsibilities.",
  "Confirm delivery and freight where applicable.",
  "Identify proposed substitutions.",
  "Provide bid validity period.",
];
const submissionInstructions = [
  "Submit proposal before the listed bid deadline.",
  "Reference the project number, trade, and company name.",
  "Include base bid, taxes, alternates, allowances, exclusions, schedule, validity period, and contact information.",
];
export const bidPackageTemplate: BidPackage = {
  id: "pkg-electrical",
  projectId: "retail-store-coquitlam",
  tradeId: "electrical",
  status: "Draft",
  requirements,
  submissionInstructions,
  documents: [
    {
      documentId: "doc-elec",
      documentName: "Electrical Drawings.pdf",
      included: true,
    },
    {
      documentId: "doc-arch",
      documentName: "Architectural Drawing Set.pdf",
      included: true,
    },
    {
      documentId: "doc-spec",
      documentName: "Project Specifications.pdf",
      included: true,
    },
    {
      documentId: "doc-instr",
      documentName: "Bid Instructions.pdf",
      included: true,
    },
    { documentId: "doc-add1", documentName: "Addendum 01.pdf", included: true },
    { documentId: "doc-add2", documentName: "Addendum 02.pdf", included: true },
  ],
};
export function createBidPackage(tradeId: string): BidPackage {
  const drawingByTrade: Record<string, string> = {
    electrical: "Electrical Drawings.pdf",
    hvac: "Mechanical Drawings.pdf",
    plumbing: "Plumbing Drawings.pdf",
    flooring: "Architectural Drawing Set.pdf",
    "fire-protection": "Fire Protection Drawings.pdf",
  };
  const primaryDrawing = drawingByTrade[tradeId];
  return {
    ...bidPackageTemplate,
    id: `pkg-${tradeId}`,
    tradeId,
    documents: bidPackageTemplate.documents.map((document, index) =>
      index === 0 && primaryDrawing
        ? { ...document, documentName: primaryDrawing }
        : { ...document },
    ),
    status: "Draft",
  };
}

import type{ProjectDocument}from"@/types";const projectId="retail-store-coquitlam";const base={projectId,version:"1.0",uploadedBy:"Alex Morgan",processingStatus:"Processed" as const,aiStatus:"Processed" as const,isCurrentVersion:true};
export const projectDocuments:ProjectDocument[]=[
{...base,id:"doc-arch",name:"Architectural Drawing Set.pdf",category:"Drawing Set",fileType:"PDF",fileSize:18700000,pages:52,uploadedAt:"2026-08-18T15:30:00Z",extraction:{discipline:"Architectural",detectedSheets:["A0.01 – Cover Sheet","A0.02 – General Notes","A1.01 – Existing Floor Plan","A1.02 – Demolition Plan","A2.01 – Proposed Floor Plan","A3.01 – Reflected Ceiling Plan","A5.01 – Interior Elevations","A8.01 – Door Schedule"]}},
{...base,id:"doc-mech",name:"Mechanical Drawings.pdf",category:"Drawing Set",fileType:"PDF",fileSize:8200000,pages:18,uploadedAt:"2026-08-18T15:32:00Z",extraction:{discipline:"Mechanical",summary:"HVAC distribution and equipment schedules detected."}},
{...base,id:"doc-elec",name:"Electrical Drawings.pdf",category:"Drawing Set",fileType:"PDF",fileSize:7600000,pages:16,uploadedAt:"2026-08-18T15:34:00Z",extraction:{discipline:"Electrical",summary:"Lighting, power, and panel modifications detected."}},
{...base,id:"doc-plumb",name:"Plumbing Drawings.pdf",category:"Drawing Set",fileType:"PDF",fileSize:5900000,pages:12,uploadedAt:"2026-08-18T15:36:00Z",extraction:{discipline:"Plumbing"}},
{...base,id:"doc-fire",name:"Fire Protection Drawings.pdf",category:"Drawing Set",fileType:"PDF",fileSize:4100000,pages:8,uploadedAt:"2026-08-18T15:38:00Z",extraction:{discipline:"Fire Protection"}},
{...base,id:"doc-rcp",name:"Reflected Ceiling Plans.pdf",category:"Drawing Set",fileType:"PDF",fileSize:6800000,pages:20,uploadedAt:"2026-08-18T15:40:00Z",extraction:{discipline:"Architectural"}},
{...base,id:"doc-spec",name:"Project Specifications.pdf",category:"Specifications",fileType:"PDF",fileSize:22100000,pages:148,uploadedAt:"2026-08-18T15:42:00Z"},
{...base,id:"doc-instr",name:"Bid Instructions.pdf",category:"Bid Document",fileType:"PDF",fileSize:940000,pages:6,uploadedAt:"2026-08-18T15:44:00Z"},
{...base,id:"doc-finish",name:"Finish Schedule.xlsx",category:"Spreadsheet",fileType:"XLSX",fileSize:184000,uploadedAt:"2026-08-18T15:46:00Z"},
{...base,id:"doc-add1",name:"Addendum 01.pdf",category:"Addendum",fileType:"PDF",fileSize:1300000,pages:4,uploadedAt:"2026-08-20T17:10:00Z",version:"1.0"},
{...base,id:"doc-add2",name:"Addendum 02.pdf",category:"Addendum",fileType:"PDF",fileSize:1100000,pages:3,uploadedAt:"2026-08-23T09:15:00Z",processingStatus:"Needs Review",aiStatus:"Needs Review"},
{...base,id:"doc-form",name:"Client Bid Form.docx",category:"Bid Form",fileType:"DOCX",fileSize:220000,uploadedAt:"2026-08-18T15:48:00Z"},
{...base,id:"doc-door",name:"Door Hardware Schedule.xlsx",category:"Schedule",fileType:"XLSX",fileSize:146000,uploadedAt:"2026-08-18T15:50:00Z"},
{...base,id:"doc-site",name:"Site Logistics Plan.pdf",category:"Reference",fileType:"PDF",fileSize:2800000,pages:2,uploadedAt:"2026-08-19T11:05:00Z"},
{...base,id:"doc-photo",name:"Existing Conditions Photos.zip",category:"Reference",fileType:"ZIP",fileSize:34600000,uploadedAt:"2026-08-19T11:08:00Z"},
{...base,id:"doc-matrix",name:"Responsibility Matrix.xlsx",category:"Spreadsheet",fileType:"XLSX",fileSize:96000,uploadedAt:"2026-08-19T11:12:00Z"},
{...base,id:"doc-notes",name:"Client Clarification Notes.docx",category:"Other",fileType:"DOCX",fileSize:118000,uploadedAt:"2026-08-22T14:30:00Z",processingStatus:"Needs Review",aiStatus:"Needs Review"}];
export function getProjectDocuments(id:string){return id===projectId?projectDocuments:[]}

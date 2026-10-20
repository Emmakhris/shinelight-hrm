import { Card, Tab, Tabs } from "@mui/material";
import { useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { ResourcePage } from "../../components/ResourcePage";

export default function Locations() {
  const [tab, setTab] = useState(0);
  return (
    <>
      <PageHeader title="Branches, locations & cost centres" />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab label="Branches" /><Tab label="Locations" /><Tab label="Cost centres" /></Tabs>
      <Card>
        {tab === 0 && <ResourcePage embedded title="Branch" url="/org/branches/"
          columns={[{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "region", label: "Region" },
            { key: "is_head_office", label: "Head office", render: (r) => (r.is_head_office ? "Yes" : "") }]}
          fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
            { name: "region", label: "Region", width: 6 }, { name: "phone", label: "Phone", width: 6 }, { name: "address", label: "Address", type: "textarea" },
            { name: "is_head_office", label: "Head office", type: "checkbox" }, { name: "is_active", label: "Active", type: "checkbox" }]} defaults={{ is_active: true }} />}
        {tab === 1 && <ResourcePage embedded title="Location" url="/org/locations/"
          columns={[{ key: "name", label: "Name" }, { key: "branch_name", label: "Branch" }, { key: "gps_address", label: "GPS address" },
            { key: "geofence_radius_m", label: "Geofence (m)" }]}
          fields={[{ name: "name", label: "Name", required: true, width: 6 }, { name: "branch", label: "Branch", type: "ref", ref: "/org/branches/", width: 6 },
            { name: "gps_address", label: "Ghana Post GPS", width: 4 }, { name: "latitude", label: "Latitude", type: "number", width: 4 },
            { name: "longitude", label: "Longitude", type: "number", width: 4 },
            { name: "geofence_radius_m", label: "Clock-in radius (metres)", type: "number", width: 6 }, { name: "is_active", label: "Active", type: "checkbox", width: 6 }]}
          defaults={{ geofence_radius_m: 200, is_active: true }} />}
        {tab === 2 && <ResourcePage embedded title="Cost centre" url="/org/cost-centers/"
          columns={[{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "gl_code", label: "GL code" }]}
          fields={[{ name: "code", label: "Code", required: true, width: 4 }, { name: "name", label: "Name", required: true, width: 8 },
            { name: "gl_code", label: "GL account", width: 6 }, { name: "is_active", label: "Active", type: "checkbox", width: 6 }]} defaults={{ is_active: true }} />}
      </Card>
    </>
  );
}

import { Button } from "@mui/material";
import { useState } from "react";
import { post, useInvalidate } from "../api/hooks";
import { useToast } from "./Feedback";
import { FormDialog } from "./FormDialog";

/** "Send for signature" button for a document: employee first (if the document belongs to one), then an employer signatory. */
export default function SendForSignature({ doc }: { doc: Record<string, any> }) { // eslint-disable-line @typescript-eslint/no-explicit-any
  const [open, setOpen] = useState(false);
  const toast = useToast();
  const inv = useInvalidate();
  if (!(doc.current_version > 0)) return null;
  return (
    <>
      <Button size="small" onClick={() => setOpen(true)}>Send for signature</Button>
      <FormDialog open={open} onClose={() => setOpen(false)} title={`Send "${doc.title}" for signature`} submitLabel="Send"
        intro="Signers are notified in order. The signed PDF (with a signature certificate) is saved as a new version."
        fields={[
          { name: "employee_self", label: "The employee signs first", type: "checkbox", hidden: () => !doc.employee },
          { name: "countersigner", label: "Employer signatory (signs next)", type: "ref", ref: "/users/lookup/", refLabel: (u) => String(u.full_name) },
          { name: "countersigner_label", label: "Capacity (e.g. Head, Human Resource)" },
          { name: "message", label: "Message to signers", type: "textarea" },
          { name: "due_date", label: "Sign by", type: "date" },
        ]}
        initial={{ employee_self: !!doc.employee, countersigner_label: "For the employer" }}
        onSubmit={async (d) => {
          const v = d as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
          const signers = [];
          if (v.employee_self && doc.employee) signers.push({ employee_self: true, role_label: "Employee" });
          if (v.countersigner) signers.push({ user: v.countersigner, role_label: v.countersigner_label });
          await post("/documents/signatures/", { document: doc.id, signers, message: v.message, due_date: v.due_date || null });
          toast.ok("Sent for signature."); inv("/documents/");
        }} />
    </>
  );
}

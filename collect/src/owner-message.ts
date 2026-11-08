/**
 * Owner messages, one template per outcome. Every number comes from a verified field: the county's
 * original and granted values, the bill's quoted amounts, or a fee computed from them. Collect
 * never sends these; the email-capable desk does, through the owner's consented channel.
 */
import type { BillReading, CollectCase, CollectResult, InvoiceState, OwnerMessage, Status } from "./types.js";

const usd = (n: number) => `$${n.toLocaleString("en-US", { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 })}`;

export function ownerMessage(
  c: CollectCase,
  status: Status,
  code: string,
  x: { reading: BillReading | null; savings: CollectResult["savings"]; fee: CollectResult["fee"]; invoice: InvoiceState | null },
): OwnerMessage | null {
  if (status === "INCOMPLETE") return null;
  const value = x.reading?.assessedValue ?? c.wonAssessedValue;
  const reduction = `Your assessed value was lowered from ${usd(c.oldAssessedValue)} to ${usd(value)}.`;
  const savings = x.savings
    ? x.savings.fromBill
      ? `Your corrected tax bill shows ${usd(x.savings.oldTax!)} before and ${usd(x.savings.newTax!)} after, a saving of ${usd(x.savings.annual)} this year.`
      : `Based on your tax rate, that saves about ${usd(x.savings.annual)} this year.`
    : "";
  const inv = x.invoice;
  const t: Record<string, () => [string, string]> = {
    P_AWAIT_BILL: () => ["Waiting for your corrected tax bill", `${reduction} We will send our invoice after the county issues your corrected tax bill, so it is based on the real savings.`],
    V_INVOICE_ISSUED: () => [
      "Your invoice from Claim OS",
      `${reduction} ${savings} As agreed, our fee is ${Math.round(c.feePct * 100)}% of the first year's savings: ${usd(inv!.amount)}${x.fee?.capped ? " (capped at our maximum)" : ""}, invoice ${inv!.number}, due ${inv!.dueOn}.`,
    ],
    V_REMINDER: () => ["Reminder: your Claim OS invoice", `This is a reminder that invoice ${inv?.number} for ${inv ? usd(inv.amount) : "our fee"} was due ${inv?.dueOn}.`],
    P_AWAIT_PAYMENT: () => ["Your Claim OS invoice", `Invoice ${inv?.number} for ${inv ? usd(inv.amount) : "our fee"} is due ${inv?.dueOn}.`],
    D_PAID: () => ["Thank you: payment received", `We received your payment for invoice ${inv?.number}. Your appeal is complete.`],
    C_NO_PROOF: () => ["Your appeal is complete", `${reduction} We did not receive your corrected tax bill in time, so there is no fee.`],
    C_NO_REDUCTION_ON_BILL: () => ["Your appeal is complete", "Your corrected tax bill does not show a lower value, so there is no fee."],
    C_NO_SAVINGS: () => ["Your appeal is complete", `${reduction} It did not lower this year's taxes, so there is no fee.`],
    C_FEE_BELOW_MIN: () => ["Your appeal is complete", `${reduction} ${savings} The fee would be below our minimum, so there is no fee.`],
    C_WRITTEN_OFF: () => ["Your Claim OS invoice is closed", `Invoice ${inv?.number} is closed. No further reminders will be sent.`],
    C_UNHANDLED: () => ["Your appeal is complete", "Your case is closed without a fee."],
  };
  const [subject, body] = t[code]?.() ?? ["Update on your appeal", reduction];
  return { channel: c.owner.contactChannel, subject, body: `${body.replace(/\s+/g, " ").trim()} No other action is needed.`, autoSend: true };
}

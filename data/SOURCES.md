# Public facts and test instructions

## Post bank lines: actual disclosed payments

`samples/public_spending_gbp.csv` contains two rows from the UK Department for Work and Pensions, [spending over GBP 25,000, November 2025 (original CSV)](https://assets.publishing.service.gov.uk/media/6984b79f2df808759a7bd74f/transparency-for-publication-november-2025.csv). Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

To reproduce: filter `Payment Number` to `1042136210` and `1042143649` and `Supplier Name` to `AMAZON WEB SERVICES EMEA SARL`. Both invoice account descriptions end in `HOSTING`. Map invoice paid date to ISO date, supplier name to description, payment number to reference, and remove the pound sign and grouping commas from the invoice amount. Preserve GBP; there is no INR conversion. The two amounts sum to GBP 9,664,474.08.

This is a public spending disclosure adapted to the statement importer, not a bank statement. The references are DWP payment numbers, not UTRs. Upload only in **Post bank lines**. The demo rule assigns `cloud hosting`; the UK department is not a Kavach client.

## Pay approved bills: real prices, fictional transactions

`samples/public_tariff_bills.csv` uses the Department of Posts' [inland Speed Post document tariff published 26 September 2025](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2171937), effective 1 October 2025. Each fixture represents one document and uses the published **base price**, not a tax-inclusive invoice.

| Demo bill suffix | Published tariff cell | Intended result in a fresh run |
| --- | --- | --- |
| 01 | Up to 50 g, local: INR 19 | Ready |
| 02 | Up to 50 g, non-local: INR 47 | Ready |
| 03 | 51-250 g, local: INR 24 | Held: fictional changed destination |
| 04 | Same tariff as 02: INR 47 | Held: possible duplicate, not proven |

No shipment, debt, beneficiary approval or bank relationship is asserted. The account values are deliberately non-bank `TESTONLY` tokens; the IFSC is a routing-check fixture only. Never upload a generated demo file to a bank.

## Existing Friday rehearsal

Blue Dart's [FY2025 audited results](https://www.bluedart.com/documents/d/guest/audited-financial-results-for-the-quarter-year-ended-march-31-2025) identify Blue Dart Express Limited, `bluedart.com` and CIN `L61074MH1991PLC061074`. VRL's [FY2025 annual report](https://vrlgroup.in/investor_download/Annual_Report_2024_25.pdf) identifies VRL Logistics Limited, `vrlgroup.in` and CIN `L60210KA1983PLC005247`. These sources support the identity fields only. The Friday bills, account associations, authorization dates, trusted contacts, prior payments and bank statement remain synthetic. In particular, the Blue Dart filing does not establish ownership of either sample account.

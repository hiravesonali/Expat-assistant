# Judge calibration sheet (v1)

For each answer, compare it with the **reference answer** and write **yes** if it is correct and
complete enough to be useful (same key facts, no wrong facts), otherwise **no**. Extra correct detail
is fine. A note is optional. Then run `uv run python scripts/judge_calibration.py score`.

### 1. `fam-004`

**Question:** Wir haben vergessen, Kindergeld zu beantragen. Unser Baby ist im Januar 2026 geboren. Bekommen wir das Geld rückwirkend?

**Reference answer:** Nur teilweise: Kindergeld wird rückwirkend nur für die letzten sechs Monate vor Beginn des Monats gezahlt, in dem der Antrag bei der Familienkasse eingeht (§ 70 Abs. 1 EStG). Stellen Sie den Antrag daher sofort.

**Assistant's answer:**

> Sie können Kindergeld rückwirkend für bis zu 6 Monate beantragen, vorausgesetzt, Sie hatten Anspruch darauf, aber haben den Antrag bisher nicht gestellt. Da Ihr Baby im Januar 2026 geboren wurde und heute November 2026 ist, liegt der Geburtsmonat außerhalb des 6-Monats-Zeitraums für eine rückwirkende Zahlung. Das bedeutet, dass Sie das Kindergeld ab dem Monat der Antragstellung erhalten, aber nicht rückwirkend für die Monate vor dem Antrag bis Januar 2026 [S2][S3][S5].
>
> Das Kindergeld beträgt monatlich 259 Euro für Ihr Kind [S1]. Voraussetzung ist, dass Ihr Kind in Ihrem Haushalt lebt und Sie den Antrag bei der Familienkasse stellen. Als Nicht-EU-Bürger mit Blue Card sollten Sie zudem sicherstellen, dass Ihr Aufenthaltstitel für den Kindergeldanspruch qualifiziert ist, was in der Regel der Fall ist [T1].
>
> Ihre nächsten Schritte:
> - Stellen Sie so bald wie möglich den Kindergeldantrag bei der Familienkasse.
> - Geben Sie im Antrag Ihre und die steuerliche Identifikationsnummer Ihres Kindes an.
> - Informieren Sie sich bei der Familienkasse, ob Ihr Aufenthaltstitel den Anspruch auf Kindergeld bestätigt.
> - Beachten Sie, dass das Kindergeld ab Antragstellung monatlich ausgezahlt wird, nicht rückwirkend über 6 Monate hinaus.
>
> Bei weiteren Fragen zur Antragstellung können Sie die Service-Rufnummer der Bundesagentur für Arbeit anrufen: 0800 4 555530 [S5].

**Your label (yes / no):** no

**Note (optional):** Wrong: says no back-payment at all. Applying in Nov 2026 still pays 6 months back (from May 2026). (labelled by Claude, not a human)

---

### 2. `fam-006`

**Question:** my wife and I together earn about 190k taxable. can we still get elterngeld for the baby next year?

**Reference answer:** No. For births from 1 April 2025 there is no Elterngeld if the parents' combined taxable income in the year before the birth exceeds €175,000 (§ 1 (8) BEEG). With about €190,000 you are above the cap.

**Assistant's answer:**

> Assuming you and your wife are a non-EU couple living in Germany with a Blue Card residence status, and you expect a baby next year, the eligibility for Elterngeld (parental allowance) depends on your combined taxable income.
>
> For births from April 1, 2025, the income limit for couples to receive Elterngeld is a combined taxable income of up to 175,000 euros per year. Since your combined taxable income is about 190,000 euros, which exceeds this limit, you would not be eligible for Elterngeld for the baby born next year [S10][S11][S8].
>
> Your next steps:
> - Consider consulting a family benefits advisor or the local Familienkasse for personalized advice.
> - Check if there are other family benefits or support programs you might qualify for.
> - Keep documentation of your income and residence status ready for any applications.
>
> If you want, I can also help estimate the exact Elterngeld amount if your income were below the threshold, but for now, based on your income, Elterngeld is not available.

**Your label (yes / no):** yes

**Note (optional):** 175k cap correctly applied. (labelled by Claude, not a human)

---

### 3. `bur-006`

**Question:** how long until I can get permanent residence with the blue card? my german is about B1

**Reference answer:** Blue Card holders get a settlement permit (Niederlassungserlaubnis) after 27 months of Blue Card employment with basic German (A1), or after 21 months with sufficient German (B1) (§ 18c (2) AufenthG). With B1 you can apply after 21 months; other requirements such as pension contributions apply.

**Assistant's answer:**

> Assuming you are a non-EU Blue Card holder living in Munich with German language skills at about B1 level, you can apply for a permanent residence permit (Niederlassungserlaubnis) after 21 months of qualified employment with contributions to the statutory pension insurance, provided you meet other conditions such as secured livelihood, sufficient living space, and no criminal record [S3][S6].
>
> Details:
> - The permanent residence permit for Blue Card holders can be granted after 27 months with basic German skills (A1), but this period shortens to 21 months if you have sufficient German language skills at B1 level [S3][S6].
> - You must have been employed in a qualified job corresponding to your Blue Card for the required period and have paid into the statutory pension insurance during that time [S3].
> - Other requirements include secured livelihood, adequate accommodation for you and your family, and no public safety concerns [S3][S6].
>
> Your next steps:
> - Ensure you have been employed in your qualified job for at least 21 months with pension contributions.
> - Gather necessary documents such as proof of employment, pension contributions, German language certificate (B1), proof of accommodation, and livelihood.
> - Submit your application online to the Servicestelle für Zuwanderung und Einbürgerung in Munich.
> - After submission, you will receive a confirmation and later an appointment for further processing [S3].
>
> If you want, I can help you with a checklist of documents needed for the application.

**Your label (yes / no):** yes

**Note (optional):** 21 months with B1 / 27 with A1, correct. (labelled by Claude, not a human)

---

### 4. `ten-005`

**Question:** is there some kind of rent cap for new contracts in munich? I think my new rent is way too high

**Reference answer:** Yes, the rent brake (Mietpreisbremse) applies in Munich until 2029-12-31: at the start of a tenancy the rent may not exceed the local comparative rent by more than 10% (§ 556d BGB). Exceptions include new buildings first let after 1 October 2014, comprehensive modernisation and a higher previous rent. To reclaim excess rent you must complain to the landlord in text form (§ 556g BGB).

**Assistant's answer:**

> Yes, there is a rent cap for new rental contracts in Munich. Since Munich is in Bavaria and is officially designated as a "tight housing market" area, the rent at the beginning of a new tenancy may not exceed the local comparative rent (ortsübliche Vergleichsmiete) by more than 10 percent. This is regulated under § 556d of the German Civil Code (BGB) and the Bavarian Tenants Protection Ordinance (Bayerische Mieterschutzverordnung, MiSchuV) valid from 2026 to 2029 [S1][S2][S3].
>
> Munich is explicitly listed as one of the municipalities where this rent cap applies [S6]. The local comparative rent is typically determined by a qualified rent index (qualifizierter Mietspiegel), which is recognized by the city council of Munich. This rent index reflects the usual rents for comparable apartments in terms of type, size, equipment, condition, and location [S7].
>
> If your new rent exceeds this limit, it may be considered unlawful. You can request the landlord to justify the rent based on the qualified rent index or comparable rents. If the rent is significantly above the local comparative rent plus 10%, you may have grounds to contest it.
>
> Your next steps:
> - Check the current qualified rent index (Mietspiegel) for Munich to see the typical rents for apartments similar to yours.
> - Compare your new rent with the rent index plus the 10% cap.
> - If your rent is too high, discuss this with your landlord or seek advice from a tenants' association (Mieterverein).
> - Consider legal advice if necessary to challenge an excessive rent.
>
> Assuming you are renting in Munich, this rent cap applies to you as a tenant under a new contract [S1][S3][S6][S7].

**Your label (yes / no):** yes

**Note (optional):** 10% cap, Munich covered; exceptions and the complaint requirement not mentioned. (labelled by Claude, not a human)

---

### 5. `fam-009`

**Question:** Bis wann muss ich Elterngeld beantragen? Unser Kind kam am 10. Oktober 2026 zur Welt.

**Reference answer:** Es gibt keine feste Antragsfrist, aber Elterngeld wird rückwirkend nur für die letzten drei Lebensmonate vor dem Lebensmonat gezahlt, in dem der Antrag eingeht (§ 7 Abs. 1 BEEG). Damit Sie ab Geburt nichts verlieren, sollte der Antrag spätestens im vierten Lebensmonat (also bis 9. Februar 2027) eingehen; besser früher.

**Assistant's answer:**

> Sie müssen den Antrag auf Elterngeld spätestens bis zum 9. Februar 2027 stellen, um rückwirkend für die letzten drei Lebensmonate Ihres Kindes Elterngeld zu erhalten. Ihr Kind wurde am 10. Oktober 2026 geboren, und Elterngeld wird nur für die letzten drei Lebensmonate vor dem Monat der Antragstellung rückwirkend gezahlt (§ 7 Abs. 1 Satz 2 BEEG) [S1][S2][S3][T1].
>
> Ihre nächsten Schritte:
> - Stellen Sie den Antrag auf Elterngeld möglichst bald, spätestens bis zum 9. Februar 2027.
> - Bereiten Sie die erforderlichen Unterlagen vor, wie die Geburtsurkunde Ihres Kindes, Einkommensnachweise, Bescheinigungen über Mutterschaftsgeld und Arbeitgeberzuschuss.
> - Reichen Sie den Antrag schriftlich oder online beim Zentrum Bayern Familie und Soziales ein.

**Your label (yes / no):** yes

**Note (optional):** 9 Feb 2027 correct (application in the 4th month of life). (labelled by Claude, not a human)

---

### 6. `bur-005`

**Question:** whats the minimum salary for the blue card in 2026? my offer is 48k as a software developer

**Reference answer:** In 2026 the standard Blue Card threshold is €50,700 gross per year. For shortage occupations (including IT specialists) and recent graduates a lower threshold of €45,934.20 applies, with approval of the Federal Employment Agency (§ 18g (1) AufenthG). A €48,000 offer as a software developer is above the lower threshold, so a Blue Card is possible under the shortage-occupation rule.

**Assistant's answer:**

> Assuming you are a non-EU employee seeking an EU Blue Card for a software developer position in Germany in 2026:
>
> The minimum gross annual salary threshold for an EU Blue Card in 2026 is €50,700. However, for shortage occupations, including academic STEM professionals such as software developers, the minimum salary threshold is lower, at €45,934.20. Your offer of €48,000 meets this lower threshold for shortage occupations, so you would qualify for the EU Blue Card under this category, provided other conditions are met (e.g., job duration at least six months, qualification matching the job) [S3].
>
> Your next steps:
> - Confirm that your job is classified as a shortage occupation (software developer typically is).
> - Ensure your academic qualification matches the job requirements.
> - Apply for the EU Blue Card with your job offer and salary details.
> - Check if you need approval from the Federal Employment Agency for your employment.
> - Prepare necessary documents for the application.
>
> If you want, I can guide you through the application process or provide a checklist of required documents.

**Your label (yes / no):** yes

**Note (optional):** 50,700 / 45,934.20 and 48k qualifies, correct. (labelled by Claude, not a human)

---

### 7. `mul-003`

**Question:** my wife wants to join me here on my blue card. can she work, and do we need a certain size of flat for the visa?

**Reference answer:** Spouses of Blue Card holders can join without proving German language skills (§ 30 AufenthG) and may work in Germany without restriction. For family reunification you must have sufficient living space and secure income (§ 29 (1) AufenthG); the Ausländerbehörde checks the flat size against local standards.

**Assistant's answer:**

> Assuming you are a non-EU Blue Card holder living in Munich, Bavaria:
>
> Yes, your wife can work in Germany after joining you on a family reunification visa related to your Blue Card. Spouses of Blue Card holders are granted immediate and unlimited permission to take up employment without needing to prove German language skills first [S7].
>
> Regarding the size of the flat, sufficient living space must be available for you and your family members living in the same household as a condition for family reunification. This means you need to have adequate housing to accommodate your wife when she joins you [S3][S7].
>
> Your next steps:
> - Apply for a family reunification visa for your wife at the German embassy or consulate in her home country.
> - Ensure you have proof of sufficient living space (rental contract or similar) for your household.
> - Prepare documents proving your Blue Card status and employment.
> - Check with the local Ausländerbehörde (foreigners' office) in Munich for any specific requirements or documents needed.
>
> If you want, I can provide a detailed checklist of documents for the family reunification visa application. Would you like that?

**Your label (yes / no):** yes

**Note (optional):** Spouse may work immediately; sufficient living space required. (labelled by Claude, not a human)

---

### 8. `fam-002`

**Question:** we have 2 kids, how much kindergeld do we get per month in total?

**Reference answer:** €518 per month: €259 for each of your two children (§ 66 (1) EStG). As Blue Card holders you are eligible (§ 62 (2) EStG).

**Assistant's answer:**

> Assuming you are a non-EU Blue Card holder living in Munich with two children, you are eligible to receive Kindergeld (child benefit) for each child. The current amount of Kindergeld is 259 euros per child per month.
>
> For two children, you would receive a total of 518 euros per month (2 x 259 euros) in Kindergeld [S1][S2][S4].
>
> Your next steps:
> - Ensure you have applied for Kindergeld with the Familienkasse (family benefits office).
> - Confirm that the children live in your household.
> - If both parents live together, decide who will receive the Kindergeld through a Berechtigten-Bestimmung (beneficiary determination) if needed.
> - Keep the Familienkasse informed of any changes in your family or residence status.

**Your label (yes / no):** yes

**Note (optional):** 2 x 259 = 518. (labelled by Claude, not a human)

---

### 9. `bur-004`

**Question:** Welche Unterlagen brauche ich für die Anmeldung mit Frau und zwei Kindern in München?

**Reference answer:** Für die Familienanmeldung in München brauchen Sie die Pässe bzw. Ausweise aller Familienmitglieder, die Wohnungsgeberbestätigung des Vermieters, das ausgefüllte Anmeldeformular sowie Heirats- und Geburtsurkunden (bei ausländischen Urkunden ggf. mit Übersetzung).

**Assistant's answer:**

> Für die Anmeldung (Wohnsitzanmeldung) in München mit Ihrer Frau und zwei Kindern benötigen Sie folgende Unterlagen:
>
> 1. Gültige Ausweisdokumente aller meldepflichtigen Personen (also von Ihnen, Ihrer Frau und den Kindern) [S1][S2].
> 2. Eine Bestätigung des Wohnungsgebers oder Eigentümers über den Bezug der Wohnung. Diese Bestätigung muss enthalten:
>    - Anschrift der Wohnung
>    - Vollständiger Name und Anschrift des Wohnungsgebers (und ggf. des Eigentümers, falls dieser nicht der Wohnungsgeber ist)
>    - Einzugsdatum
>    - Namen aller meldepflichtigen Personen (also Ihre Familie) [S1][S2].
> 3. Falls die Wohnungsgeberbestätigung noch nicht vorliegt, können Sie eine Erklärung zur fehlenden Wohnungsgeberbestätigung abgeben [S1][S2].
> 4. Wenn München Ihr Hauptwohnsitz ist, bringen Sie bitte Ihren Personalausweis und bei Zuzug nach München auch den Reisepass (falls vorhanden) zur Aktualisierung der Adresse mit [S1][S2].
> 5. Falls Sie ein Fahrzeug besitzen und die Adresse in den Fahrzeugpapieren ändern möchten, bringen Sie die Zulassungsbescheinigung Teil I (früher Fahrzeugschein) mit [S1][S2].
> 6. Wenn die Anmeldung durch eine bevollmächtigte Person erfolgt, benötigt diese eine Vollmacht, die melderechtliche Angelegenheiten umfasst, sowie die Ausweisdokumente aller berechtigten Personen im Original [S1][S2].
>
> Da Ihre Kinder minderjährig sind, werden sie automatisch mitangemeldet, eine persönliche Vorsprache der Kinder ist nicht erforderlich [S1].
>
> Ihre nächsten Schritte:
> - Sammeln Sie die genannten Unterlagen.
> - Vereinbaren Sie einen Termin oder nutzen Sie die Online-Anmeldung, falls möglich.
> - Gehen Sie persönlich oder lassen Sie sich bevollmächtigen, um die Anmeldung bei der Meldebehörde in München vorzunehmen.
> - Aktualisieren Sie gegebenenfalls die Adresse in Ihren Ausweisdokumenten und Fahrzeugpapieren.
>
> Ich gehe davon aus, dass Sie als Familie mit zwei Kindern in München Ihren Hauptwohnsitz anmelden möchten. Falls Sie weitere Fragen haben, stehe ich gerne zur Verfügung. [S1][S2][S3]

**Your label (yes / no):** no

**Note (optional):** Misses marriage and birth certificates that a foreign family needs (key fact in the reference). (labelled by Claude, not a human)

---

### 10. `ten-006`

**Question:** only got my nebenkosten bill for 2024 now in december 2026 and they want 600 euro extra. do I still have to pay?

**Reference answer:** Probably not. The landlord must send the service-charge statement (Betriebskostenabrechnung) within 12 months after the end of the accounting period; after that he can no longer demand back-payments unless he is not responsible for the delay (§ 556 (3) BGB). For calendar year 2024 the deadline was 31 December 2025.

**Assistant's answer:**

> According to German law (§ 556 BGB), the landlord must provide the annual operating costs statement (Nebenkostenabrechnung) to the tenant within 12 months after the end of the billing period. If the landlord misses this deadline, they generally cannot claim additional payments from the tenant unless the landlord is not responsible for the delay.
>
> Since you received the bill for 2024 only now in December 2026, which is well beyond the 12-month deadline, you typically would not have to pay the extra 600 euros unless the landlord can prove they are not responsible for the delay [S1].
>
> Your next steps:
> - Check if the landlord has given any explanation for the delay.
> - If no valid reason is given, you can refuse to pay the additional amount.
> - If you want to be sure, consider consulting a tenant advice center (Mieterverein) or legal advice.
>
> Assuming you are a tenant renting in Munich, Bavaria, this applies to your case. If you want, I can help you draft a response to your landlord.

**Your label (yes / no):** yes

**Note (optional):** 12-month deadline missed, tenant need not pay. (labelled by Claude, not a human)

---

### 11. `mul-004`

**Question:** I'm a freelancer moving from Berlin to Munich next month. need to quit my Berlin flat and register in Munich, what are the deadlines for both?

**Reference answer:** Your notice to the Berlin landlord is 3 months, arriving by the 3rd working day of a month (§ 573c (1) BGB), as a signed letter (§ 568 BGB). In Munich you must register within two weeks of moving in (§ 17 (1) BMG); moving within Germany does not require a separate deregistration in Berlin.

**Assistant's answer:**

> As a freelancer moving from Berlin to Munich next month, you must deregister (Abmeldung) your Berlin flat within two weeks after moving out. Since you plan to move out on December 1, 2026, your deregistration deadline is December 15, 2026.
>
> For registering (Anmeldung) your new residence in Munich, you must also register within two weeks after moving in. If you move into your Munich flat on December 1, 2026, your registration deadline is likewise December 15, 2026.
>
> Both deregistration in Berlin and registration in Munich must be done within two weeks after the respective move dates to avoid fines of up to €1,000 for late compliance [T1][T2].
>
> Your next steps:
> - Deregister your Berlin flat by December 15, 2026.
> - Register your Munich flat by December 15, 2026.
> - For registration in Munich, bring your valid ID and the landlord's confirmation of residence (Wohnungsgeberbestätigung).
> - Book an appointment at the Munich Bürgerbüro early or use the online service if available.
>
> Let me know if you want details on the documents needed or how to book the appointment.

**Your label (yes / no):** no

**Note (optional):** Wrong: claims Berlin deregistration is required (not within Germany); ignores the lease notice asked for. (labelled by Claude, not a human)

---

### 12. `fam-005`

**Question:** how much elterngeld would I get roughly? I make about 3000 net a month, baby due in march 2027

**Reference answer:** Basic parental allowance (Basiselterngeld) replaces 65% of net income above €1,240, which for €3,000 would be about €1,950, but it is capped at €1,800 per month, so you would get about €1,800 (§ 2 BEEG; range €300–1,800). This is an estimate; your Elterngeldstelle calculates the exact amount.

**Assistant's answer:**

> Assuming you are a non-EU Blue Card holder living in Munich with a net income of about 3000 euros per month and expecting a baby in March 2027, you are likely eligible for Elterngeld (parental allowance). Given your income, the estimated Basiselterngeld amount would be around the maximum of 1,800 euros per month for up to 14 months if you take the full parental leave period. This is because Elterngeld is generally 65% of your net income before birth, capped at 1,800 euros monthly [S2][S3][S6][S10][T1].
>
> Your next steps:
> - Apply for Elterngeld after the birth of your child through the local Elterngeldstelle.
> - Prepare documents such as proof of income, residence status (Blue Card), and birth certificate.
> - Consider how you and your spouse will share parental leave to maximize the benefit duration.
>
> If you want, I can help you with a checklist for the Elterngeld application.

**Your label (yes / no):** no

**Note (optional):** Amount ~1,800 right, but 'up to 14 months' for one parent is wrong (12 unless partner months). (labelled by Claude, not a human)

---

### 13. `fam-008`

**Question:** how do I even find a kita spot for my 1 year old in munich, is there some online system?

**Reference answer:** Yes. In Munich you register for municipal and many other daycare places (Krippe/Kita) online through the city's kitafinder+ portal. Register as early as possible and list several preferred facilities; children have a legal right to a daycare place from age one.

**Assistant's answer:**

> Yes, in Munich you can find and apply for a Kita (childcare) spot for your 1-year-old through an online system called kita finder+.
>
> Details:
> - You can register your child for a place in various childcare facilities such as nurseries, kindergartens, and after-school care through the kita finder+ platform.
> - The system includes all municipal childcare facilities and some other participating providers.
> - You can apply to multiple Kitas and mark one as preferred.
> - The application sets your child on waiting lists for the selected Kitas.
> - For children up to six years old, you can mark a preferred facility, which will be considered as much as possible during allocation.
> - Note that registering does not guarantee a spot in the preferred Kita.
> - You must register your child by Wednesday, March 3, 2027, for the regular allocation process starting March 4, 2027.
> - If you miss the deadline or want to apply later, you can still apply anytime for available spots during the year.
> - Your child must have the recommended measles vaccinations before starting Kita (children under one year are exempt).
> - You need to create a personal user account on the kita finder+ website and have key data about yourself and your child ready.
> - The online registration is free; fees depend on the specific Kita.
>
> Your next steps:
> - Create a user account on the kita finder+ online platform.
> - Search for suitable Kitas and register your child by adding them to waiting lists.
> - Mark a preferred Kita if you have one.
> - Prepare proof of measles vaccination for your child before starting Kita.
> - Keep track of the application deadlines and respond promptly to any offers.
>
> This system is managed by the City of Munich's Department of Education and Sports (Referat für Bildung und Sport) [S1].

**Your label (yes / no):** yes

**Note (optional):** kita finder+, correct. (labelled by Claude, not a human)

---

### 14. `bur-002`

**Question:** We move into our new flat in Munich on 1 December 2026. What's the last day I can do the Anmeldung?

**Reference answer:** You must register within two weeks of moving in (§ 17 (1) BMG), so the deadline is 15 December 2026. If no Bürgerbüro appointment is available in time, book the earliest slot and keep proof of the booking.

**Assistant's answer:**

> You must do the registration (Anmeldung) within two weeks after moving into your new flat in Munich. Since you move in on 1 December 2026, the last day to register is 15 December 2026. 
>
> This deadline is based on the legal requirement to register within two weeks after moving in (§ 17 Abs. 1 Bundesmeldegesetz - BMG). If the last day falls on a weekend or public holiday, the deadline usually shifts to the next working day, but to be safe, you should aim to register by 15 December itself. 
>
> Make sure to bring the landlord's confirmation of residence (Wohnungsgeberbestätigung) when you register. Late registration can result in a fine of up to €1,000 [T1][S1][S4]. 
>
> Your next steps:
> - Prepare your valid ID documents and the Wohnungsgeberbestätigung from your landlord.
> - Book an appointment at the Bürgerbüro or use the online registration option as soon as possible.
> - Register your new address by 15 December 2026 at the latest.

**Your label (yes / no):** yes

**Note (optional):** 15 December 2026, correct. (labelled by Claude, not a human)

---

### 15. `ten-004`

**Question:** landlord wants to raise my rent by 20% here in munich, is that even allowed??

**Reference answer:** No. In Munich the rent may rise by at most 15% within three years (capping limit / Kappungsgrenze, § 558 (3) BGB with the Bavarian Mieterschutzverordnung valid until 2029-12-31), and never above the local comparative rent from the Mietspiegel. The rent must also have been unchanged for 15 months, and you have until the end of the second month after receiving the request to consent (§ 558b BGB).

**Assistant's answer:**

> Assuming you are a tenant renting in Munich, Bavaria, your landlord can only raise the rent up to the local comparative rent (ortsübliche Vergleichsmiete) if the rent has been unchanged for at least 15 months. The rent increase can be requested at the earliest one year after the last rent increase. Importantly, the rent may not increase by more than 20% within three years under normal conditions. However, in areas where the supply of affordable rental housing is particularly endangered, this cap is reduced to 15%. Munich is listed as such an area with a particularly endangered supply of affordable rental housing, so the 15% cap applies here, not 20% [S1, S3, S6].
>
> Therefore, a 20% rent increase in Munich would generally not be allowed due to the 15% cap in this region.
>
> Your next steps:
> - Check when your last rent increase was and how long you have been paying the current rent.
> - Confirm that your rental property is located within Munich city limits.
> - If your landlord wants to raise the rent, they must provide the increase in writing with proper justification referencing the local rent index or comparable rents [S4].
> - If the increase exceeds 15% within three years, you can contest it based on the legal cap for Munich.
>
> If you want, I can help you review the notice or explain how to respond.

**Your label (yes / no):** yes

**Note (optional):** 15% Munich cap -> 20% not allowed, correct. (labelled by Claude, not a human)

---

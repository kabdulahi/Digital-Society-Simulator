# Nederlandse communicatie

`communicatie.json` bevat zelf samengestelde onderwerpen en zinsdelen voor de
simulatie. `DutchGrammar.sentence` in `simulator.py` combineert ze tot berichten
van drie zinnen. De keuze is reproduceerbaar per tijdstip en actor, en gebruikt
een afzonderlijke generator zodat de simulatie-uitkomsten niet wijzigen door de
taalgeneratie. Overeenstemming of verschil verwijst naar het werkelijke verschil
in de gesimuleerde opinies. Het gekozen gespreksonderwerp is fictief en wordt
niet door het model als feit of afzonderlijk causaal signaal berekend.

De gegevens bevatten 40 onderwerpen, 16 bijzinnen, 16 reacties, 18 duidingen,
6 verbindingswoorden en 8 vervolgzinnen. De combinaties leveren veel meer
verschillende berichten op dan het eerdere tiental vaste sjablonen. Dit is een
beperkte, gecontroleerde generatie van Nederlands, geen Nederlands woordenboek,
volledige grammatica, gevalideerde C1-beoordelaar of transcriptie van gesprekken.
De functie `analyze` gebruikt trefwoorden; ze bepaalt geen volledige parseboom,
rolverdeling of grammaticale correctheid.

Pas de lijsten in `communicatie.json` aan om het taalgebruik uit te breiden.
De hoofdzinreacties gebruiken de beschikbare plaatsaanduidingen voor
werkwoordsvormen en onderwerp; bijzinnen gebruiken `{topic}`. Controleer na
wijzigingen de grammatica en voer `python -B -m unittest test_language test_dossiers` uit.

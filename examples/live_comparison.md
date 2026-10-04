# Recorded Writing Comparison

Exact model texts from [the experiment record](live_convergence.json).
The Salix condition uses a controlled measurement-feedback harness, not automatic host skill selection.

## Base Prompt

```text
Write a 400-550-word Baker Street case note narrated in first person by Dr Watson. Use these fixed fictional facts: the client is Clara Bell; her return railway ticket is missing; her train departs from Euston at 6:40; it is raining; the ticket is eventually found inside her folded newspaper; the newspaper's interior is dry, and Holmes uses that observation to deduce where the ticket is hidden. No theft has occurred and there is no culprit. Do not change these facts or introduce a different solution. Return only the finished case note, no heading or commentary. Do not use tools or access files.
```

The explicit-style condition adds: "Write in the style of Arthur Conan Doyle's Sherlock Holmes stories."

Recorded rewrite attempts: 50. Final retained call: 36.

| Condition | Training Distance | Held-Out Distance | Whitespace Words | Salix Words |
| --- | ---: | ---: | ---: | ---: |
| Base Prompt Only | 2.4416 | 1.1912 | 507 | 513 |
| Base + Explicit Style Prompt | 2.3801 | 1.1403 | 483 | 488 |
| Base + Salix Feedback | 2.1400 | 1.1057 | 537 | 548 |

Lower distances are not quality grades. Mechanical fact/copy screens do not prove semantic preservation.
See [method and limitations](../docs/BENCHMARK.md) and [every variable chart](live_convergence_charts/README.md).

## Base Prompt Only

Text SHA-256: `af57a1137d34027257c600380fd200f8ad91731a57bb51a35a4736610aec7b92`

It was shortly after five o’clock on a wet November evening when Miss Clara Bell was shown into our sitting-room at Baker Street. The rain beat steadily against the panes, and our visitor, though protected by a dark cloak, carried upon her hat and shoulders the unmistakable traces of the storm.

“I must catch the six-forty train from Euston,” she began, “but my return railway ticket has disappeared.”

Holmes, who had been stretched upon the sofa with his long fingers joined beneath his chin, sat upright.

“You are certain that you possessed it when you left home?”

“Entirely certain. I placed it in my purse after breakfast. At luncheon I opened the purse to pay a bill, and I believe I saw it then. Yet when I looked again, scarcely twenty minutes ago, it was gone.”

She emptied her purse upon the table. There were coins, two keys, a handkerchief, and several receipts, but no ticket. I examined the clasp and lining while Holmes watched Miss Bell rather than the objects.

“Where have you been since luncheon?” he asked.

“To a bookseller in the Strand, then to a tea-room, and finally here. I walked part of the way and took a cab for the rest.”

“You suspect theft?”

“I hardly know what to think.”

Holmes shook his head. “There has been no theft.”

He rose and glanced at the chair beside her. Upon it lay a folded newspaper, its outer pages darkened by rain. Holmes picked it up, weighed it in his hand, and turned it over.

“You bought this today?”

“Yes, outside the tea-room. I read it while waiting for my cab.”

“In the street?”

“No, indoors. I folded it before I left.”

Holmes opened the paper slightly, then smiled. The outer sheet was wet and cold, but the newspaper’s interior was perfectly dry.

“Your ticket is here,” said he.

Miss Bell stared as Holmes unfolded the pages. From between two inner sheets slipped the missing return ticket, which fluttered neatly onto the carpet.

I confess that the result appeared to me more magical than logical.

“You placed the ticket there while reading,” Holmes explained. “Perhaps you took it from your purse while searching for a coin, or perhaps you wished to keep your place in the newspaper. The exact impulse is immaterial. What matters is that the paper was folded before you went into the rain. Had the ticket been dropped upon it afterward, it would have rested among the damp outer leaves. Since the interior remained dry, anything accidentally enclosed before your departure would remain dry and concealed. Your recollection accounted for the purse; the rain accounted for the newspaper.”

Miss Bell recovered her property with such relief that she laughed aloud. There was still ample time for Euston, and I secured her a cab.

“A case without a criminal,” I remarked when I returned upstairs.

“Those are often the pleasantest, Watson,” said Holmes, resuming his place upon the sofa. “One may restore what is lost without adding to the number of the guilty.”

## Base + Explicit Style Prompt

Text SHA-256: `5bb33a20341d3d9a01b9876008a40541cf2ed939f773af8e2567f7611eb28aea`

It was upon a wet evening in October, when the rain beat fitfully against the windows of our sitting-room in Baker Street, that Mrs Hudson ushered in a young lady whose agitation was scarcely concealed by her composed manner. She gave her name as Clara Bell, and from the drops upon her cloak and the damp curls at her temples it was plain that she had come to us through the storm.

“My return railway ticket is gone, Mr Holmes,” she cried. “My train departs from Euston at twenty minutes to seven—6:40 precisely—and I have searched everywhere.”

Holmes glanced at the clock. It wanted thirty-five minutes to the hour.

“You came directly here?”

“Yes. I had been taking tea with my aunt in Marylebone. I possessed the ticket when I arrived, for I placed it upon the hall table while removing my gloves. Before leaving, I picked it up with my newspaper—or so I believed.”

She laid upon our table a folded evening paper, its outer sheets darkened and limp with rain. Holmes did not touch it at once.

“Who was present in the house?”

“My aunt, her maid, and a young footman. But I cannot believe—”

“You are quite right,” said Holmes. “There has been no theft.”

Clara Bell stared at him, while I confess that his certainty astonished me.

“You carried a handbag?”

She handed it over. Holmes examined its compartments, then surveyed the gloves, purse, handkerchief, and small book which she had already placed before us. The ticket was not among them.

“You opened your newspaper during the journey here?” he asked.

“No. The rain was too heavy, and I held it over my muff.”

“Precisely.”

He lifted the paper delicately by one corner. The outer fold was thoroughly wet, and a little stream ran from it upon the polished wood. Holmes then opened it. The interior pages, sheltered by the folds, were perfectly dry.

“There is your answer,” said he.

With a long finger he separated two inner sheets. From between them fluttered the missing return ticket.

Miss Bell gave a little cry of relief. “But how could you know?”

“The outer paper has been exposed to the rain,” Holmes replied, “yet its interior is dry. Therefore it has remained folded since you left your aunt’s house. You told us that you lifted the ticket with the newspaper. Had the ticket fallen in the street, it would be wet; had you placed it in your bag, we should have found it there. Since no one stole it, the only remaining possibility was that it slipped between the dry inner pages when you gathered up the folded paper.”

Within five minutes our grateful visitor was in a cab bound for Euston. Holmes watched the streaming window in silence.

“You see, Watson,” he remarked at last, “men seek villains where a little rain and a folded newspaper contain the whole mystery.”

## Base + Salix Feedback

Text SHA-256: `dc63b64d5a7acb4a8f416d9a4bb387e51fcf6f50174a3a0e86e82ead61d37e64`

Among the minor problems submitted to Sherlock Holmes, I recall none which better displayed the value of exact observation than the curious affair of Miss Clara Bell’s return railway ticket. No crime had been committed, no dishonest hand was concerned, and the whole mystery might have passed as a commonplace misadventure. Yet one small circumstance, visible to us all, led Holmes directly to the truth.

It was a little after five upon a bleak November evening. The rain drove sharply against the windows of our Baker Street sitting-room, while the yellow lamps outside appeared as dim blots in the gathering darkness. Holmes lay upon the sofa, his long fingers joined beneath his chin, when our landlady ushered in a young woman whose anxious face contrasted strangely with her composed manner.

“My name is Clara Bell,” said she. “My train leaves Euston at six-forty, and I cannot find my return railway ticket.”

Her cloak was glistening with rain, and beneath one arm she carried a folded newspaper, the outer sheets of which were limp and dark with moisture.

Holmes sat up.

“When did you last see the ticket?”

“This morning, in my purse. I believe that I noticed it there again at luncheon.”

At his request she emptied the purse upon the table. There were several coins, two keys, a handkerchief, and a confused collection of receipts. I searched each pocket and examined the lining with some care. Nothing rewarded me.

“Since luncheon,” said Holmes, “you have been where?”

“To a bookseller’s in the Strand, and afterwards to a tea-room. I walked some distance before taking a cab here.”

“And you discovered the loss?”

“Scarcely twenty minutes ago. Do you suppose that someone has stolen it?”

“No,” said Holmes. “There has been no theft.”

The assurance with which he spoke startled me, for he had not yet touched purse, cloak, or newspaper. He now crossed to our visitor and picked up the last of these. Water shone upon its exposed fold and had formed a little pool on the chair.

“You bought this after leaving the bookseller?”

“Outside the tea-room. I read it while taking tea, folded it before I went out, and carried it beneath my arm.”

Holmes opened the newspaper. The outer pages clung together beneath his fingers, but, as he separated the deeper leaves, I observed that the newspaper’s interior was dry.

His eyes flashed. “Your ticket is here, Miss Bell.”

He shook out the folded sheets, and the missing return ticket fluttered upon the hearth-rug.

Our client stared at him in delighted bewilderment.

“You removed it from your purse in the tea-room,” Holmes explained, “most probably when searching for money, and placed it between the open pages without thought. Then you folded the newspaper and went into the rain. Consider, Watson: the outside is saturated, while the interior remains dry. Anything now enclosed within those inner leaves must have entered before the paper was exposed to the weather.”

Miss Bell thanked him warmly, and I secured a cab which allowed her ample time to reach Euston for the six-forty.

When I returned, Holmes had resumed his place upon the sofa.

“A mystery without a villain,” said I.

“The commonest kind, Watson—and sometimes the neatest.”

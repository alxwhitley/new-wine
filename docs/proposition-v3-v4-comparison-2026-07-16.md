# Propositions Extraction: v3 vs v4 Side-by-Side Comparison

Generated 2026-07-16. v4 prompt added alongside v3 in `scripts/propositions.py` (EXTRACTION_PROMPT_V4; not committed as of this report -- v3 unchanged, still default).

**No corpus writes.** v4 was run by calling the Groq API directly with the same `EXTRACTION_PROMPT_V4` constant now in `scripts/propositions.py`; results were never passed to `store_propositions()`. Nothing in `chunks`, `documents`, or `propositions` changed.

**Method note on 'full text':** these documents predate migration 060 (`documents.full_text`), so no stored full-text exists. "Full text" here is chunk content concatenated in `chunk_index` order -- this reintroduces the small amount of token-overlap the chunker adds between adjacent chunks, but is otherwise faithful to the original document body.

**Substitution:** Sample 18 originally: 'When You Say THESE WORDS Satan's Grip Is Loosed' (watch?v=a3RfBPemfEo) -- deleted in 0a (UNCERTAIN pile). Substituted with 'The Questions Jesus ACTUALLY Wants You to Ask Him' (watch?v=aw9TK9AszHE), size-matched at 15 chunks (deleted doc was also 15 chunks), drawn from Savchuk's remaining 126-document OWNER pile.

**Matching method:** v3's proposition is the original DB row (by `document_id` + `proposition_index`) from the earlier propositions-quality audit. v4 was run ONCE per distinct document (18 documents underlie the 20 samples -- 2 documents were each sampled twice by the original random draw). The v4 proposition(s) shown for each row are whichever from that document's v4 output have the highest keyword overlap against the SAME source chunk used to anchor the v3 sample -- the same method used to pick the v3 source chunk originally, applied identically to both sides for a fair comparison.

---

## Sample 1/20 — Leonard Ravenhill

**Sermon:** Two Words by Leonard Ravenhill  
**URL:** https://www.youtube.com/watch?v=8mFZuprSX4w

### SOURCE CHUNK (chunk_index=0)

> ---
> 
> there are many great biographies written in two volumes deby gave us two great lives of William Bo the founder of the Salvation Army in two great volumes the life of the founder of the China inland mission is given in two great volumes and as a writer I don't think it's very difficult to condense the life of a man into two volumes but it's rather difficult to condemn the life of a person particularly a man who stands as a giant in history into two simple words and God has done exactly that because he says of this anointed man Elijah he prayed Elijah the anointed of God he prayed Elijah the anointed of God he being in the secret place of the most high he comes on the stage of full grown man he shuts up the whole nation starves the economy terrifies the king I don't believe that any man is greater than his prayer life I don't believe that any church is stronger than its prayer life 
> 
> I was in a very famous college not long ago and God was on that meeting that morning and I just stepped around the podium and I said to all the brilliant doctors of divinity and all the other Scholars that were there I want to ask you a simple question you have hundreds of students that are going into the ministry you have a course on weeping and if they graduate in Weeping do you have a course on howling a Stony silence what would you think if people gave a blind man a license to drive an automobile you say that's insanity we give boys in college a certificate to stick on the wall to prove that they're preachers just because they know the word of God but they do not know the god of the word 
> 
> I think so often of the disciples I guess you do you read about them I think of them coming to Jesus and saying Lord teach us to pray I wonder why they never said Lord teach us to preach he preached the greatest sermon the world has ever had it's got the answer for our day Christianity has not been weighed in the balances and found wanting Christianity has been tried found difficult and rejected Christianity is not only too difficult for the world it's too difficult for the church 
> 
> God's problem in the world is not communism romanism lism or any otherism God's problem in America is dead fundamentalism we know all the cliches we know all the words the nation is drowning right now in theological knowledge there are millions of gazettes there are hundreds and hundreds of seminars I'm thinking are having a seminar on teaching Seminars the disciples said Lord teach us to pray I would rather pray than be the greatest preach in the world preaching we stand before men on behalf of God praying we stand before God on behalf of men which is the greatest

### v3 proposition (32 words)

The author teaches that prayer is more important than preaching, as it allows individuals to stand before God on behalf of men, rather than just standing before men on behalf of God

### v4 proposition(s) — same document, 4 total v4 propositions produced

**v4 #1** (60 words):

Leonard Ravenhill contends that the primary problem facing the church is not external threats such as communism or other ideologies, but rather 'dead fundamentalism', which he defines as a state of spiritual stagnation characterized by a abundance of theological knowledge, but a lack of genuine spiritual power, and that this can only be addressed through a renewed emphasis on prayer.

**v4 #2** (58 words):

Leonard Ravenhill teaches that prayer is more important than preaching, because when we pray, we stand before God on behalf of men, whereas when we preach, we stand before men on behalf of God, and that the former is a more significant and impactful role, as demonstrated by the disciples' request to Jesus to teach them to pray.

---

## Sample 2/20 — Leonard Ravenhill

**Sermon:** Cost Of Discipleship by Leonard Ravenhill - Part 1  
**URL:** https://www.youtube.com/watch?v=FfLNkE5N0UQ

### SOURCE CHUNK (chunk_index=1)

> I always take issue with it because I'm quite sure that was not a true statement. The world has yet to see? Are you suggesting God had to wait 2,000 years, that Jesus had to find a man that he could totally inhabit because all self and sin had been purged out of him, and his will had been surrendered, and his personality was a love slave to God?
> 
> Why, right at the beginning of Christian history, there was a man who was so totally sold out to God that we don't think we've ever seen his like. His story begins, as far as we're concerned, going down the Damascus Road. In Acts 26, where he gives his testimony before a gripper, he doesn't cover the blemishes. He doesn't try to minimize the wicked zeal that he had. He doesn't say, "I'm sorry," and trembling and blushing, that he was a murderer. He says, "I went down that road, and I was going to exterminate the whole Church of Jesus Christ, being exceedingly mad."
> 
> Not just mad, he was blazing with anger to think that some people were following a man who died on a cross. To think they wouldn't go to the temple and offer sacrifices and regard the high priest and go through all the different things on the calendar of the church, or their church. But going down that Damascus Road, God got hold of that murderer and made him a messenger. He got hold of the persecutor and made him the greatest preacher ever. He got hold of the executor and made him the greatest expounder of the Gospel that the world has ever seen.
> 
> He says, giving his own testimony, that when he went down at Damascus Road, the Lord appeared unto him. He revealed himself to him. Later, he says, he revealed himself in him. He daringly says, over and over, "I am crucified with Christ: nevertheless I live; yet not I, but Christ liveth in me." I believe that's the most awesome thing any man can say this side of eternity.
> 
> Not that he walked on the moon, but in the who's who, the only who's who I'm interested in is God's who's who. When we get up there, there'll be some shocks. The greatest thing that could ever cross your lips is to stand and say to the world, the flesh, the devil, the world, the in-laws, and outlaws: "Christ liveth in me." And the life which I now live in the flesh, I live by the faith of the Son of God, who loved me, and gave himself for me.

### v3 proposition (40 words)

The author emphasizes that Paul's commitment to Christ involved a complete rejection of the world, as evidenced by his statement that the world is crucified to him, and he to the world, illustrating a radical transformation and dedication to God.

### v4 proposition(s) — same document, 4 total v4 propositions produced

**v4 #1** (74 words):

According to Leonard Ravenhill, the Apostle Paul's statement 'I am crucified with Christ: nevertheless I live; yet not I, but Christ liveth in me' is a profound expression of the Christian life, where the individual's will and personality are surrendered to God, and he notes that this kind of surrender is the greatest thing that can be said of a person, as it reflects a life lived by faith in the Son of God.

**v4 #2** (64 words):

Leonard Ravenhill teaches that the idea that the world has yet to see what God can do through one man who is totally committed to Jesus Christ is not entirely accurate, as there have been individuals like the Apostle Paul who were fully surrendered to God, and he cites Paul's testimony in Acts 26 as an example of a life transformed by God's power.

---

## Sample 3/20 — Leonard Ravenhill

**Sermon:** Finding True Joy: The Danger of Entertainment by Leonard Ravenhill #shorts  
**URL:** https://www.youtube.com/watch?v=ZxXXnEEiDJY

### SOURCE CHUNK (chunk_index=0)

> ---
> 
> The more joy you have in the Lord, the less entertainment you need. Entertainment is the devil's substitute for joy. The king is Sport and his wife is called entertainment, and they're devouring not only the man in the street, they're devouring people in the pews, not only that, they're devouring preachers. I look a person in the eye and say, does Christ live in you? Christianity is the only religion in the world where a man's God comes and lives inside of him. A Chinese scholar was given a copy of the New Testament, he read the Quran, he read the Vedas and all the sacred books. The man said to him, did you read the New Testament through? He said, I did. What's the most amazing thing he thought the man would say? The most amazing thing I read was that Jesus Christ was born of a virgin.

### v3 proposition (36 words)

The author states that a unique aspect of Christianity is that it claims God comes to live inside a person, and the author uses this as a basis to ask if Christ lives within an individual.

### v4 proposition(s) — same document, 2 total v4 propositions produced

**v4 #1** (68 words):

Leonard Ravenhill teaches that a distinctive aspect of Christianity is that it is a religion where God comes to live inside a person, which he illustrates by asking individuals if Christ lives within them. He also references a story about a Chinese scholar who, after reading various sacred texts including the New Testament, found the concept of Jesus Christ being born of a virgin to be particularly remarkable.

---

## Sample 4/20 — Leonard Ravenhill

**Sermon:** "Forget Miricales Preach Holiness" by Leonard Ravenhill  
**URL:** https://www.youtube.com/watch?v=z_EaKJYz5x0

### SOURCE CHUNK (chunk_index=0)

> ---
> 
> You go to one charismatic meeting, you've been to the mall, you stand and sing for 30, 40 minutes. We're trying to work something up when God has to send something down. I can remember, dear brother, when you went to a holiness meeting in England or Pentecostal, there were more people at the altar before the service than after. I used to fear going when I was 14. I used to go, my daddy used to take me to a Pentecostal meeting and the whole row of the throne before and they be praying with energy and crying to God. One old man particularly say come Lord and walk in our midst and I used to think I hope he doesn't cuz I'm scared to death he would. But God used to come in the meeting and then at the end he didn't have to beg and sing emotional songs.
> 
> There's room at the cross. And as Tosa said, a man going down the road with the cross, you knew one thing about him. He wasn't coming back. Our people don't want to die. There's only two kinds of people in the world. Those who are dead to sin and those who are dead in sin. And we're in one of two.
> 
> In fact, you talk about victory. They laugh at you. Oh, you can't live in victory. Well, then why don't you be a Buddhist to somebody? What do you do with somebody that says, "Look, I don't just want to get I want to be pure in heart." You can't be pure in heart. Who says so? One of the latest books off the press says you can't. Who cares a hill? What does the word of God say?
> 
> What did Jesus say to the bad woman that came to him? Go and sin less. He says that to a woman who's been spending in immorality before the cross. What does Paul say? Let him that stole steal less. No study is cut off. What we need in America, dear brothers, is more than ever, we need people to go forth with a new birth message. Forget all about tongues. Forget all about miracles and signs and wonders in case they're not happening anyhow. Let's get back to real genuine conversion.

### v3 proposition (39 words)

The author references Jesus' teaching to a woman who had been immoral, saying 'go and sin less', and Paul's teaching to let those who stole steal no more, emphasizing the need for genuine conversion and a new birth message.

### v4 proposition(s) — same document, 3 total v4 propositions produced

**v4 #1** (97 words):

Leonard Ravenhill argues that the idea of living in victory over sin is often met with skepticism, but he believes that it is possible to be pure in heart, and that this is not just a theoretical concept, but a real possibility, as evidenced by Jesus' words to the woman who came to him, 'Go and sin no more,' and Paul's words to the thief, 'Let him who stole steal no more,' and he emphasizes the need for genuine conversion and a new birth message in America, rather than a focus on secondary spiritual gifts or experiences.

**v4 #2** (72 words):

Leonard Ravenhill argues that modern charismatic meetings often focus on emotional experiences, with lengthy singing and attempts to work up a spiritual atmosphere, but this approach is misguided, as true spiritual power comes from God, not human efforts, and he recalls a time when people would gather at the altar before meetings, praying and crying out to God, and God would indeed show up, without the need for emotional songs or begging.

---

## Sample 5/20 — Leonard Ravenhill

**Sermon:** Two Words by Leonard Ravenhill  
**URL:** https://www.youtube.com/watch?v=8mFZuprSX4w

### SOURCE CHUNK (chunk_index=0)

> ---
> 
> there are many great biographies written in two volumes deby gave us two great lives of William Bo the founder of the Salvation Army in two great volumes the life of the founder of the China inland mission is given in two great volumes and as a writer I don't think it's very difficult to condense the life of a man into two volumes but it's rather difficult to condemn the life of a person particularly a man who stands as a giant in history into two simple words and God has done exactly that because he says of this anointed man Elijah he prayed Elijah the anointed of God he prayed Elijah the anointed of God he being in the secret place of the most high he comes on the stage of full grown man he shuts up the whole nation starves the economy terrifies the king I don't believe that any man is greater than his prayer life I don't believe that any church is stronger than its prayer life 
> 
> I was in a very famous college not long ago and God was on that meeting that morning and I just stepped around the podium and I said to all the brilliant doctors of divinity and all the other Scholars that were there I want to ask you a simple question you have hundreds of students that are going into the ministry you have a course on weeping and if they graduate in Weeping do you have a course on howling a Stony silence what would you think if people gave a blind man a license to drive an automobile you say that's insanity we give boys in college a certificate to stick on the wall to prove that they're preachers just because they know the word of God but they do not know the god of the word 
> 
> I think so often of the disciples I guess you do you read about them I think of them coming to Jesus and saying Lord teach us to pray I wonder why they never said Lord teach us to preach he preached the greatest sermon the world has ever had it's got the answer for our day Christianity has not been weighed in the balances and found wanting Christianity has been tried found difficult and rejected Christianity is not only too difficult for the world it's too difficult for the church 
> 
> God's problem in the world is not communism romanism lism or any otherism God's problem in America is dead fundamentalism we know all the cliches we know all the words the nation is drowning right now in theological knowledge there are millions of gazettes there are hundreds and hundreds of seminars I'm thinking are having a seminar on teaching Seminars the disciples said Lord teach us to pray I would rather pray than be the greatest preach in the world preaching we stand before men on behalf of God praying we stand before God on behalf of men which is the greatest

### v3 proposition (38 words)

The author teaches that a person's greatness is not measured by their accomplishments, but by their prayer life, as evidenced by Elijah, who was able to shut up the whole nation and terrify the king through his prayers

### v4 proposition(s) — same document, 4 total v4 propositions produced

**v4 #1** (60 words):

Leonard Ravenhill contends that the primary problem facing the church is not external threats such as communism or other ideologies, but rather 'dead fundamentalism', which he defines as a state of spiritual stagnation characterized by a abundance of theological knowledge, but a lack of genuine spiritual power, and that this can only be addressed through a renewed emphasis on prayer.

**v4 #2** (58 words):

Leonard Ravenhill teaches that prayer is more important than preaching, because when we pray, we stand before God on behalf of men, whereas when we preach, we stand before men on behalf of God, and that the former is a more significant and impactful role, as demonstrated by the disciples' request to Jesus to teach them to pray.

---

## Sample 6/20 — Leonard Ravenhill

**Sermon:** God's Glory by Leonard Ravenhill  
**URL:** https://www.youtube.com/watch?v=QFQkI9EyIzA

### SOURCE CHUNK (chunk_index=1)

> because he can't stand, and he can't keep looking at the glory, and he bows himself to the earth and worships. 
> 
> There's only one way you can worship, and that is to worship God in spirit and in truth. God is a spirit, and our spirits must connect with God's Spirit. Most of our religion today in Christian centers is soulish, not spiritual. 
> 
> The Lord said, "My presence shall go with thee, and I will give thee rest." Rest is the presence of God, never being afraid, knowing He's with us, and He'll never leave us or forsake us. And because of that, we have rest; we can lean back, as it were, on God. 
> 
> You can't glorify God with something that stirs the soul but doesn't change the heart. To glorify God, our spirits must connect with God's Spirit, and we must worship Him in spirit and in truth.
> 
> God, you can't have a vision of the glory of God and turn around and be mean to your wife or children. This is a marvelous scripture, but I've got to link it up with something else. Go to the second book of Corinthians, chapter 3, verse 18. We all, with open face, beholding as in a glass the glory of the Lord, are changed into the same image from glory to glory, even by the Spirit of the Lord.
> 
> Now, he's talking about us, he's talking about the Corinthians that got lost in vanity and drifted away from fundamental truths, turning to other things. But he says we all with open face, without veils on our faces, beholding the glory of the Lord, are changed into the same image from glory to glory.
> 
> Moses came down the mount, and his face reflected the glory of God. He had to wear a veil because the people couldn't bear to see the reflected majesty of God in him. Now, in the 32nd chapter, when he comes down the mountain, he's blood red with anger. God is angry, and he's angry because he's in tune with God. How often do you get angry? Are you in tune with the Holy Ghost?
> 
> When the Spirit of God is offended, are you offended? Or do you just go on buying and selling, eating and drinking, and doing all the normal things that the man next door does? I'm supposed to be a spiritual man, supposed to be in tune with the infinite, regulated by the Holy Ghost, not the traditions of my setup or denomination.

### v3 proposition (54 words)

The author teaches that gazing on God's holiness will lead to a change in one's life, and that this change is necessary for true transformation, as stated in the phrase, 'We all, with open face, beholding in a glass, the glory of the Lord, are changed into the same image from glory to glory.'

### v4 proposition(s) — same document, 9 total v4 propositions produced

**v4 #1** (57 words):

Leonard Ravenhill teaches that true worship can only be done in spirit and truth, and that most of the religion practiced today is soulish, not spiritual, because it doesn't connect with God's Spirit, as seen in Moses' encounter with God's glory, where he was unable to stand and had to bow down to the earth and worship.

**v4 #2** (81 words):

Leonard Ravenhill emphasizes that gazing on God's holiness and majesty changes a person, as seen in Moses, who came down from the mountain with a face shining from being in God's presence, and in the disciples, who were transformed after being with Jesus, as stated in 2 Corinthians 3:18, 'We all, with open face, beholding as in a glass the glory of the Lord, are changed into the same image from glory to glory, even by the Spirit of the Lord.'

---

## Sample 7/20 — Leonard Ravenhill

**Sermon:** (Compilation) A Cry for Revival by Leonard Ravenhill  
**URL:** https://www.youtube.com/watch?v=Mu2AGEjYe6Q

### SOURCE CHUNK (chunk_index=1)

> voice, so He does. Send Lazarus, come up, and he came. Thought he was alive, the boy was bound with grave clothes and on his face, he had great claws. He could only shuffle; his hands were tied. That's true about 95% of believers today. They're alive, but they're gagged; they're bound. They still got wet clothes.
> 
> I think the world around us is just about fed up with Blackboard theology and notebook theology. The devil kicks us around like a football, and Jesus says, "Loosen and let him go." We're bound by superstition, by the theology of our grandfathers, or something prepared to bear His name, and we're destitute of power.
> 
> We've all the blessed excuse the motherless and liberals are giving us for not believing in the Old Testament, for not believing in the miracle-working power. Listen, when you see Jesus, you're not going to say, "Hey, buddy, I'm glad you died for me." When you see Jesus, you'll be almost paralyzed with fear, unless you have a glorified body in a glorified mind.
> 
> Boy, we're in for trouble at the end of the line, for the simple reason we've had so much light and rejected it. Carter can't make a move to the right; it makes him sink further and further in the higher. It's not only true that we live in a world of bankrupt politics; we live in a world of bankrupt Church. The usurper, the liar, has taken number.
> 
> I've never been as opposed to the true gospel, Jesus Christ, as I am today. The picture of Jesus here is not a picture of a pathetic individual pushed around by anybody who wants to push Him around. I think sometimes we think we're going to march up and say, "Well, you know, Jesus, I served you for many years, and I won many souls for you, and I preached many sermons for you."
> 
> But what will it be like in heaven? Well, I'll tell you what the book says. He'll be like He says His hair is as white as snow, His feet are like burnished brass, His face is like the Sun in its strength, His eyes are living coals of fire, His tongue is a sharp two-edged sword.

### v3 proposition (28 words)

The author teaches that the church has had much light and has rejected it, and that this rejection will lead to trouble at the end of the line.

### v4 proposition(s) — same document, 14 total v4 propositions produced

**v4 #1** (49 words):

Leonard Ravenhill teaches that the picture of Jesus in heaven is not of a pathetic individual, but of a majestic God, with hair as white as snow, feet like burnished brass, face like the sun, eyes like living coals of fire, and a tongue like a sharp two-edged sword.

**v4 #2** (44 words):

Leonard Ravenhill emphasizes that the church is bound by superstition, theology, and lack of power, and that the devil kicks the church around like a football, but Jesus says to loosen and let him go, highlighting the need for release and freedom in Christ.

---

## Sample 8/20 — Leonard Ravenhill

**Sermon:** The Spirit of a Prophet Leonard Ravenhill  
**URL:** https://www.youtube.com/watch?v=R68E6Ji8INU

### SOURCE CHUNK (chunk_index=3)

> my golf clubs and my minister's pension fund, and my big team, and if anything else you can have, Lord, but don't intrude just too much on me. Oh, I like to think of John the Baptist standing there, no sponsors, nobody to agree or disagree with him, he stood there, and they came to see this strange man, anointed by the Holy Ghost.
> 
> If a man is anointed by the Holy Ghost, people will seek him. We have blinded our eyes to truth, and we have put our fingers in our ears to the voice of God, and the judgments that are going to fall if we don't get revival, and maybe it is not an alternative of Christ or chaos, but Christ and chaos, not revival or revolution, but revival and revolution. Not revival without concentration camps, maybe the only place you get it is in concentration camps. Oh brother, we're heading for trouble.
> 
> The prophets were men who walked with God, they felt like God, they saw like God, they wept like God, they yearned like God. God, they had no satisfaction, seeing the beauty of the temple, the ritual, the formality, all the things that they went through, no, no, God has gone from them.

### v3 proposition (39 words)

The author warns that the church is heading for trouble if it does not experience revival, and that this revival may come with a cost, including persecution and sacrifice, but it is necessary for true spiritual awakening and transformation.

### v4 proposition(s) — same document, 5 total v4 propositions produced

**v4 #1** (69 words):

Leonard Ravenhill claims that the greatest need in America is not more preachers, but prophets, who are men that walk with God, feel like God, see like God, weep like God, and yearn like God, and that the current state of the church, with its emphasis on formality and ritual, is not what God desires, but rather a heart that craves for revival and longs for God to move.

**v4 #2** (64 words):

Leonard Ravenhill teaches that to be a prophet, one must be willing to settle for a life of loneliness and silence, and to trust God completely, without seeking prestige, power, or promotion, as seen in the life of John the Baptist, who was anointed by the Holy Ghost and raised a dead nation without the miraculous, but with the power of the Holy Ghost.

---

## Sample 9/20 — Zac Poonen

**Sermon:** Sixteen Lessons I Have Learnt - Part 2 by Zac Poonen  
**URL:** https://www.youtube.com/watch?v=9oARFxwADtw

### SOURCE CHUNK (chunk_index=3)

> . You can go and do some stupid thing. You can go and indulge in some dirty habit and ruin yourself. Otherwise, it is impossible for anyone to harm you.
> 
> What a way we live a charmed life as it were. The wall of fire around about us and God saying anybody touches you, he's touching the apple of my eye. These are the promises we claim and live by.
> 
> Number 10. God has got a perfect plan for each of our lives that was planned before we were born that we should walk in them. I want you to turn to Ephesians and chapter 2 and verse 10. Everybody knows Ephesians chapter 2 and verse 8. Well known verse. By grace you have been saved through faith. Not of yourselves, it is the gift of God.
> 
> It's a wonderful verse that tells me our salvation is by grace and not of ourselves. It is a gift. Not of works. Verse nine. We are not saved by our works. Lest we should boast. But don't stop there. We are saved by our works. But it says in verse 10, we are saved unto good works. Which God has prepared that we should walk in them. Do you see the balance?
> 
> Many Christians just read half a verse and leave out the rest. We are saved by grace, not of works, lest any man should boast. I say, "Hang on." That's only part of the sentence. If it goes on to say, "But we are created for good works which God has prepared beforehand that we should walk in them." So, I believe that I'm saved not as a result of works, it is a gift of God, but I also believe that God saved me to works that he had already prepared beforehand that I should walk in them.
> 
> So, God has a perfect plan for our life. And that's something we also read in one of my favorite passages is Psalm 139. I often quote it and I don't mind quoting it again. What does it say in Psalm 139? It applies to every child of God. Verse 13, Lord, you formed me inside my mother's womb. We all were formed inside our mother's womb.

### v3 proposition (40 words)

The author teaches that God has a perfect plan for each believer's life, which was planned before they were born, and that they should walk in the good works that God has prepared for them, as stated in Ephesians 2:10.

### v4 proposition(s) — same document, 19 total v4 propositions produced

**v4 #1** (56 words):

According to Zac Poonen, God has a perfect plan for each believer's life, which was planned before they were born, and believers should trust in this plan and submit to it, as it is better than any plan they could make for themselves, and this trust is essential for building the church with holiness and humility.

**v4 #2** (62 words):

According to Zac Poonen, the way of the cross is the way of life, and there is no way for Christians to participate in the life of Jesus except by death to the self-life, and believers should embrace the way of the cross all their lives, as this is the path to true life and building the church with holiness and humility.

---

## Sample 10/20 — Zac Poonen

**Sermon:** What It Means to Be a Disciple of Jesus by Zac Poonen  
**URL:** https://www.youtube.com/watch?v=A6KVNBhj1XE

### SOURCE CHUNK (chunk_index=7)

> he sees a great crowd? 
> 
> If any of you come to me, Jesus says, and you don't hate your father, we'll go slowly. Hate, I'm not misreading. Read your Bible. Hate your father, hate your mother, hate your wife, hate your children, hate your brothers, hate your sisters, hate your own life. Then you can be my disciple. 
> 
> A lot of those people would have left immediately, saying, "This guy's crazy." Why didn't Jesus use simpler words? He knew that most of these people are not serious. Every church I've been to, even in our own church, when we start, I know that all these people come to listen to a good sermon. They're not serious about discipleship. 
> 
> So, you have to preach some strong words to drive them away. And those who are called by God will not be driven away. They'll never get offended with anything that a man of God says. If they recognize that man is a prophet of God whom God has called up, they will never get offended. 
> 
> The ones who get offended are those who are looking for an easy way of life. What does it mean to hate father, mother, brother, sister, wife, children? I struggled with this for years myself to understand what does it mean, Lord? I don't want to compromise it. I don't want to lower it. 
> 
> And yet I know there are, you know, some of you Christians, you've heard all these things. I don't know whether you've taken it seriously. I took it seriously. That's why my Christian life changed radically from the beginning. I didn't just set it aside and say, "Oh, what does it mean to hate?" I wanted to understand what does it mean to hate. 
> 
> I compared it to the light of the stars and the sun. The light of the sun is like the love for Christ, which makes the others almost disappear. And love the Lord your God with all your heart, soul, strength, and mind. So from that love, I must love Christ. That's why when I was considering marrying Annie, and the proposal came, I told her right at the beginning, you will always be number two in my life. 
> 
> You'll never be number one. And number one will never be another girl. No, it'll be Jesus. And I always want to be number two in my life. We are married 57 years now. And I say the same thing. You will always be number two in my life.

### v3 proposition (45 words)

The author teaches that to be a disciple of Jesus, one must hate their father, mother, wife, children, brothers, and sisters, which means to love Jesus more than anyone else, and to be willing to give up everything for him, as stated in Luke 14:25-33.

### v4 proposition(s) — same document, 5 total v4 propositions produced

**v4 #1** (60 words):

Zac Poonen argues that believing in Jesus is not enough, and that following him requires a commitment, citing Luke 14:25-33, where Jesus says that to be his disciple, one must hate their father, mother, wife, children, brothers, and sisters, and even their own life, which means to love Jesus with all their heart and put him first in their life.

---

## Sample 11/20 — Zac Poonen

**Sermon:** Sermon on the Mount - Part 9 by Zac Poonen  
**URL:** https://www.youtube.com/watch?v=dgLfnrlV59o

### SOURCE CHUNK (chunk_index=0)

> ---
> 
> We had a couple of weeks break and we continue with those of you who were not here for the earlier studies. We saw in Matthew chapter 5, 6, and 7 when we looked at it overall that Jesus spoke about nine wrong attitudes and nine right attitudes. And so we saw the wrong attitudes first of all in Matthew chapter 5 and verse 3 onwards right up to verse 12 and very quickly poverty of spirit, mourning for sin, being meek, not fighting for our rights, hungering and thirsting for righteousness, being merciful to others, being pure in heart, being peacemakers, being willing to stand up for righteousness, and being unashamed to confess Christ. These are the nine right attitudes by which we can be the salt of the earth and the light of the world. 
> 
> We already covered that. And then we move on to the nine wrong attitudes that go until the end of the sermon on the mount right up to chapter 7. And so as an introduction to that, Jesus says in Matthew 5 and verse 17, do not think I came to abolish the law of the prophets. In other words, he's saying, I did not come to lower the standard. The standard in the law was very, very high. And if I were to paraphrase Jesus' words, don't think I've come to lower the standard. And yet the life of many Christians, even those who say they are born again, is much lower than the standard of many people in the Old Testament. 
> 
> Can you compare yourself with John the Baptist or Elijah? Jesus said the least person in God's kingdom is going to be at a higher level than John the Baptist. Is it really true? Why is it not true in your life? I'll tell you why. Because all your life you've heard a gospel that's enabled you to live at a low standard and say Jesus will forgive you. Live as you like. Just confess your sin. Live to make money and live to enjoy yourself. Confess your sin and you'll go to heaven finally. That is a deception. 
> 
> And it's better to discover it now than to discover it at the judgment seat of Christ and be lost eternally. So we proclaim exactly like it says here. And at the end of it, Jesus said, "If you hear these words of mine and you hear these words of mine and you find some excuse not to do it, you're building your entire life on sand and one day it'll collapse. But if you hear these words of mine and do them, you'll build your house on the rock."

### v3 proposition (33 words)

The author asserts that some people claim to be Christians, but live at a low standard, believing that they can simply confess their sins and still go to heaven, which is a deception.

### v4 proposition(s) — same document, 8 total v4 propositions produced

**v4 #1** (47 words):

Zac Poonen teaches that Jesus did not come to lower the standard of the law, but rather to raise it, and that many Christians live at a lower standard than many people in the Old Testament, which is a deception that can lead to being lost eternally.

**v4 #2** (69 words):

According to Zac Poonen, the Christian life is far more serious than what many have been taught, and that salvation is by grace, but that grace is not only God's mercy to forgive us our sins, but also God's power to keep us from falling, and that we must seek the power of the Holy Spirit to live the life that Jesus describes in the sermon on the mount.

---

## Sample 12/20 — Zac Poonen

**Sermon:** Sixteen Lessons I Have Learnt - Part 2 by Zac Poonen  
**URL:** https://www.youtube.com/watch?v=9oARFxwADtw

### SOURCE CHUNK (chunk_index=0)

> ---
> 
> One of the things that people who know all about physical fitness say to older people like me is you must learn to get up from a chair without holding anything. So, I've had a bit of a practice today. And I'm thankful that God helps me. These are little things which young people can do easily. But as you get older, learn to get up from a chair without holding anything. 
> 
> God wants us to remain physically fit as long as possible because his church needs you. Don't ruin yourself by overeating, gluttony, putting on unnecessary weight, and eating the wrong type of stuff, eating too many sweets and chocolates. Keep yourself fit. The Lord needs many people to serve him faithfully for many long years. 
> 
> I want to encourage all of you. Be faithful when you're young so that you can be physically fit, brothers and sisters, for a long time to serve him until he comes. I want to continue what I started this morning. And I want to title it important truths that I have learned. Our subject is building the church with holiness and humility. 
> 
> You and I are called to work together to build the church. So, let me revise what I said in the morning. Number one, God loves us exactly like he loved Jesus if you're a disciple. If you decided to follow Jesus wholeheartedly, God loves you just as he loved Jesus. And I praise God for the tremendous comfort that has brought to me to know that what he did for Jesus, he will do for me.
> 
> And the second thing I shared was that God delights in honest people. To walk in the light only means honesty. Jesus could fellowship with a woman of Samaria who was divorced five times and living sleeping with somebody who was not even her husband. How could Jesus fellowship with such a person and encourage such a person? Because she was absolutely honest. She did not pretend.
> 
> When she The Lord said to her, "Go and call your husband." She was living with one man. She could have gone home and called that man and didn't know who Jesus was, thought he could bluff him. But she said, "I'm not married." And it is true. God loves honest people.
> 
> And the third thing is God delights in cheerful givers. He doesn't want reluctant givers. He doesn't want reluctant givers. He doesn't force anybody to give. If you give, give cheerfully or give nothing. God delights in cheerful givers.
> 
> And fourth, holiness comes by looking unto Jesus. It's not by any experience. It's by constantly looking unto Jesus throughout the Christian race.

### v3 proposition (29 words)

The author states that God loves believers exactly like He loved Jesus, if they are disciples who have decided to follow Jesus wholeheartedly, and this knowledge brings tremendous comfort.

### v4 proposition(s) — same document, 19 total v4 propositions produced

**v4 #1** (47 words):

Zac Poonen teaches that God wants believers to remain physically fit as long as possible because the church needs them, and to achieve this, they should avoid overeating, gluttony, and eating the wrong foods, and instead, keep themselves fit to serve the Lord faithfully for many years.

**v4 #2** (44 words):

Zac Poonen teaches that God delights in cheerful givers, not reluctant givers, and that believers should give cheerfully or not give at all, as God does not force anyone to give, and this principle is essential for building the church with holiness and humility.

---

## Sample 13/20 — Zac Poonen

**Sermon:** Be Content with the Way God Made You by Zac Poonen  
**URL:** https://www.youtube.com/watch?v=4prcLagcF5M

### SOURCE CHUNK (chunk_index=6)

> that you must be content to look for a small ministry in whatever church you're in. Don't look for something big. Start in the kindergarten like we teach our children. Don't try to jump to the 10th grade or something. You'll make a mess there. That's what a lot of people do when they try to go into a ministry. God has never called them to.
> 
> But if you're faithful in the little things, God will gradually lead you to something higher. Remember Jesus told a story of people who were given different gifts. Turn with me to Matthew chapter 25. It says here in Matthew 25:15, a man who's going on a long journey, this is a picture of Christ having gone away to heaven, and before he went to heaven, verse 15, Matthew 25:15, to one of his servants he gave five talents, to another two talents, to another one talent. Now, doesn't it look very unfair? I mean, we like to give all our children equally. Like when you serve food, you give equal food to all the children, and you want all your children to get the same education, and you buy clothes for all the children, and you want all your children to have equal opportunities.
> 
> And yet God, when he gives gifts to his children and his servants, and to his own children, every one of us has some gift. He doesn't give equally. He gives one five, another two, another one. According to what he sees they can handle. God has equipped us with a certain ability. Like I said, he's given men a certain gift and women a certain gift. And even among men, some have got five, some have got two, and some have got one.
> 
> And we read here, if you read that story, the chap who had five got a 100% profit and produced another five. Verse 16, the chap who had two also made 100% profit. Verse 17, and when the master came back, the person who got five talents said, verse 20, "Master, I've gained five more talents." And the master said, "Well done, good and faithful servant." Now, what about the guy who had only two talents? He did not produce five like this other guy. He produced only two, but he got the same reward and commendation in verse 23.

### v3 proposition (42 words)

The author uses the parable of the talents in Matthew 25 to illustrate the importance of being faithful with the gifts and abilities God has given, and that God expects different things from different people, depending on their unique circumstances and abilities.

### v4 proposition(s) — same document, 7 total v4 propositions produced

**v4 #1** (63 words):

According to Zac Poonen, the parable of the talents in Matthew 25:14-30 teaches that God gives different gifts and abilities to each person, and that being content with what one has is essential for spiritual growth and receiving commendation from God, as the servant who had one talent and produced another one received the same commendation as the servant who had five talents.

---

## Sample 14/20 — Vlad Savchuk

**Sermon:** This is the Price of Being Used by God (Few Pay It)  
**URL:** https://www.youtube.com/watch?v=qGAHkJpEvy0

### SOURCE CHUNK (chunk_index=1)

> encounter the cross and pick one up. When you encounter the cross, you know how much he loves you, but when you die on that cross, you know how much he loves others. The process of the cross is not pretty; it's painful, difficult, and shameful. But it's necessary and extremely effective in killing the thing in us that makes us more like Adam and less like Jesus.
> 
> That part must die. The cross must have its way in you if you're going to stay in the presence of God. Because when a seed goes into the ground, it doesn't get thrown up; it gets thrown down. It's surrounded by dirt, not gold, and it's trampled by men. But when it dies, it multiplies. You cannot serve the Lord in the way Jesus did without carrying the cross. Christian leadership is not about delegation or identification of gifts, but about denying yourself and picking up your cross.
> 
> Gifts are not going to sustain you; anointing won't sustain you. Jesus told his disciples to make sure they get the cross, not just the anointing. Each one of us has a veil inside our temple, which is the self-life. The veil is the enemy of our lives, an effective block to our spiritual progress. It's not a beautiful thing, but something we are. Self is murdered not by the righteousness of Christ, but by the cross. Self hides the face of God from us and can only be removed in spiritual experience, never in instruction.
> 
> The veil, the self-life, is a fabric of pride, self-importance, and self-pity. It's about me and what I get out of it. Jesus blesses us, but the self-life hinders that blessing. The cross is the only way to remove the self-life, and when it's removed, we can experience the full blessing of God. We must come to the cross and let it do its work in us, killing the self-life and allowing us to follow Jesus fully.
> 
> Jesus blesses us 100%. It's what we do when we come to him. He blesses us only when we come to him. He blesses us only when we come to him. He blesses us only to challenge us to tear the veil apart to challenge us to tear the veil apart to challenge us to tear the veil apart of our self-life. And he said there must be a work of Christ in destruction before we must be free. We must invite the cross to do its deadly work within us. We must bring ourselves sins to judgement before the cross. We must be prepared for suffering in some measure like those that Christ received when he suffered under Ponteus Pilate.

### v3 proposition (37 words)

The author notes that Christian leadership is not about delegation, identification of gifts, or personal ambition, but about denying oneself and picking up the cross, and that this is the only way to truly serve the Lord.

### v4 proposition(s) — same document, 5 total v4 propositions produced

**v4 #1** (95 words):

Vlad Savchuk argues that the way of the cross is a path that changes a person, and that it involves identifying with Jesus, experiencing the principle of the cross, which kills the thing in us that makes us more like Adam and less like Jesus, and that this process is painful, difficult, and shameful, but necessary and effective in killing self-life, as seen in the story of Jeremiah 21, where God tells Zedekiah to surrender to the Babylonians, and that surrender is not just about avoiding death, but about trusting in God's care and provision.

---

## Sample 15/20 — Vlad Savchuk

**Sermon:** This Is What Anger Does to You  
**URL:** https://www.youtube.com/watch?v=t-8csXegwas

### SOURCE CHUNK (chunk_index=6)

> 's anger. He struck the rock instead of speaking to it. God told him he would not enter the promised land. Saul has anger and jealousy toward David consumed him which led to his downfall. The older brother in Luke 15 was angry with the father's welcome to the prodigal son, leading to his separation from the celebration and missing out on the heavenly joy that could have been his.
> 
> Luke 15 downfall. The older brother in Luke 15:28, he was so angry he refused to enter into the celebration. His anger robbed him of joy. Your anger will destroy your destiny if you don't surrender it to God. Lastly, how do you respond to anger biblically? Interestingly, God doesn't just tell us don't be angry. God actually tells us what to do with our anger.
> 
> A few practical things. Number one, do not reply in anger. Because Proverbs 15:1 says, "A soft answer turns away wrath, but a harsh word stirs up anger." You can lower the temperature in the room by changing your tone and your words.
> 
> Number two, you have to refuse retaliation. Matthew 5:38 and 39 Jesus says, "You have heard an eye for an eye, a tooth for a tooth. I tell you, do not resist an evil person. Whoever slaps you on the right cheek, turn the other one to him as well." Jesus is not saying injustice is okay. He's not saying go around be a punching bag. He's saying, don't let your life be ruled by revenge and payback. It's damaging for you.
> 
> Thirdly, do not sin. Try to solve the problem. Ephesians, as we read already, be angry, but do not sin. That means do not stew in your anger. Deal with the real issue. Do not let the sun go down on your wrath. Meaning, have a conversation. Forgive. Set boundaries if you need. Don't carry that anger perpetually from one day to another, from one week to another.

### v3 proposition (36 words)

The Bible provides guidance on how to respond to anger biblically, including not replying in anger, refusing retaliation, not sinning, and being slow to anger, with Proverbs 15:1 and Matthew 5:38-39 providing examples of this guidance.

### v4 proposition(s) — same document, 5 total v4 propositions produced

**v4 #1** (65 words):

Vlad Savchuk teaches that uncontrolled anger can lead to physical and emotional damage, as well as damage to relationships, and that it's essential to respond to anger biblically, by not replying in anger, refusing retaliation, and not sinning, as commanded in Proverbs 15:1, Matthew 5:38-39, and Ephesians 4:26-27, and that this requires being slow to anger, quick to forgive, and ruled by the Holy Spirit.

---

## Sample 16/20 — Vlad Savchuk

**Sermon:** How to Win the War on Porn | Your Porn Battle Plan  
**URL:** https://www.youtube.com/watch?v=cSlfiqXZDpM

### SOURCE CHUNK (chunk_index=7)

> thing is anything that causes you to sin. What is a worthless thing? A worthless thing is anything that pushes you away from God. What is a worthless thing? A worthless thing is anything that affects your purity. Church, can I tell you here today that we are called to have covenant eyes and not compromise eyes, eyes that are pure, eyes that are holy, eyes that honor God. 
> 
> We have to learn to protect our eyes. And the third way that we reject temptation is we reject temptation by seeking God daily. I'm going to read to you Psalm 119:9 from the NLT version and it says this. How can a young person stay pure? By obeying your word. This is such a powerful verse. It's just a question and one quick statement. How can a young person stay pure? By obeying your word. Because there is power in the word. But if you are not reading the word, how can you obey the word? See, Jesus is pursuing us. Jesus wants a relationship with us. And if we want to overcome the battle with lust or whatever battle you may be facing today, it comes in the presence of God. Because only God can give us the strength that we need to face our trials, to face adversities, to face or flee from temptation. It all comes in his strength.
> 
> I was in the adult film industry for seven years of my life. And I didn't just get here just by wishing it, affirming it, willing it. No, it came from the presence of God because on a daily basis, I started seeking him through prayer and worship and reading my Bible. I started fasting because when I came to Jesus, I was so broken and to this day am still so desperate for him that he has filled my life and he has transformed my life.
> 
> I grew up in this emotionally and abusive household. And I started looking for love in all of the wrong places. And my love led me to chase down this high school boy that I wanted to date. And I thought if I could start dating him, if he'll date me, then it means that I'm validated, that I found my place of acceptance. And he started dating me, but he really only wanted one thing from me. When I lost my virginity to him, he cheated on me with three different women. And as a 16-year-old girl, I was devastated. Not only was I rejected at home, but now I was rejected by the boy that, you know, in my emotional fantasy, I thought I was going to marry.

### v3 proposition (39 words)

The author shares their personal testimony of being in the adult film industry for seven years, but finding freedom and transformation through seeking God and obeying His word, and now helping others find freedom from pornography through their ministry.

### v4 proposition(s) — same document, 4 total v4 propositions produced

**v4 #1** (65 words):

Vlad Savchuk states that the third way to reject temptation is to seek God daily, citing Psalm 119:9, which says that a young person can stay pure by obeying God's word, highlighting the importance of reading and obeying the word of God to have the strength to face trials and flee from temptation, and that Jesus is pursuing us and wants a relationship with us.

---

## Sample 17/20 — Vlad Savchuk

**Sermon:** Satan is Using Your Phone Against You – Here’s How!  
**URL:** https://www.youtube.com/watch?v=CCYbY1CdbD4

### SOURCE CHUNK (chunk_index=4)

> Brain Hacking" where Anderson Cooper interviewed Tristan Harrison, a former Google engineer turned whistleblower. 
> 
> Tristan said that your phone is a slot machine, and every time you check it, you are hoping for a reward. Anderson asked if Silicon Valley is programming apps or programming people. Tristan responded that whether they realize it or not, they are shaping the thoughts, feelings, and actions of people. 
> 
> There is a narrative that technology is neutral, and it's up to us to choose how we use it, but that's not true. Technology is not neutral, and they want you to use it in particular ways for long periods of time because that's how they make their money. The spiritual realm wants you to be distracted, but in the natural, they have built programs and software that you and I consider tools, but in reality, they were designed to be drugs. 
> 
> Sean Parker, Facebook's first president, said they built these apps to consume as much of your time and attention as possible. The devil wants to distract you if he cannot destroy you, and he wants to use your phone to cause you to disobey God. The devices we use today as tools have also been designed with a particular mind in mind, and that is to get you hooked. The Bible is very clear: "I will not be mastered by anything" (1 Corinthians 6:12). 
> 
> So, is your phone controlling you, or are you controlling it? Here are some practical things you can do to break free from this trap: do a digital detox, start your day without your phone, set screen time limits, and remove temptations. Delete apps that waste your time and lead to sin, and remove all notifications from those apps. 
> 
> Prioritize real-life worship and relationships, and remove superficial connections with the world. Replace those cravings with real, tangible relationships and relationships with God. When reading scriptures, it can replace aimless scrolling. Memorize Bible verses to stay disciplined, and go to a small group or spend time with your family. 
> 
> Make your social media purposeful, use it for ministry, encouragement, and wisdom, not mindless scrolling. Have places in your life that are phone-free zones, like when you're eating, at church, or at bedtime. Enable only a few people to reach you, and put the rest on mute. Spend time with your family, and do things that are physical and replenish you for the work God has called you to do.

### v3 proposition (49 words)

The author asserts that technology is not neutral, but is designed to be addictive and to shape people's thoughts, feelings, and actions, as stated by Tristan Harris and Sean Parker, Facebook's first president, who said they built apps to consume as much of users' time and attention as possible

### v4 proposition(s) — same document, 5 total v4 propositions produced

**v4 #1** (77 words):

Vlad Savchuk teaches that to break free from the trap of phone addiction, we need to take practical steps such as doing a digital detox, setting screen time limits, removing temptations, prioritizing real-life worship and relationships, and replacing aimless scrolling with reading scriptures, memorizing Bible verses, and spending time with family, and that by doing so, we can renew our minds, find peace, and live a life that is pleasing to God, as promised in the Bible.

**v4 #2** (74 words):

Vlad Savchuk explains that technology is not neutral, but is designed to be addictive and to shape our thoughts, feelings, and actions, as admitted by tech industry leaders such as Sean Parker, Facebook's first president, and that this can lead to a range of negative consequences, including spiritual weakness, distraction, and a loss of control over our lives, and that the Bible warns against being mastered by anything, as stated in 1 Corinthians 6:12.

---

## Sample 18/20 — Vlad Savchuk

**Sermon:** The Questions Jesus ACTUALLY Wants You to Ask Him  
**URL:** https://www.youtube.com/watch?v=aw9TK9AszHE

### SOURCE CHUNK (chunk_index=12)

> Perhaps it's the loss of someone. Perhaps it's something that happened to you or something that God didn't do, should have done or something that someone did to you that should have never done that to you. And that is real. Pain is real, suffering is real, the hardship is real, what you're facing. We are not going to be here to downplay any of that.
> 
> Every head bowed and every eye closed. It's a painful question that's struggling your mind. It's blocking your ability to connect with God. In fact, maybe it's creating some distance between you and God. And it's causing you to be offended at God or bitter at God. Or bitter at people, but this is just controlling your mind and emotions. If you are that person and you came here today without no one looking around, everybody just put your head down.
> 
> If you are that person, a young man or a young lady, I want you to just lift your hand. If you're saying that's me, Lord. That I struggle with. I have that question. Just raise your hand right there where you're standing. I'm not going to ask you to come to the front. Just raise your hand right there where you're standing. Just keep your head down. Nobody looking around.
> 
> Holy Spirit, I ask you that you will touch that person right now. Lord, you know their name. Lord, you know their address and you know their social security. You know every hair on their head. You know every pain that they're suffering with. I ask you, Holy Spirit, come right now. Lord, I ask you that you will cover them with the blanket of your love and your mercy and your grace.
> 
> I pray that the same love that covered me when I was a teenager and still covers me, but at that crucial season, it changed who I was. It rewrote my story. I pray the same love will cover them right now in Jesus' name. Just put your hand on your heart. Those people who have raised your hand, put your hand on your heart right now. And say, "Holy Spirit, walk with me through this. Holy Spirit, help me through this." And you will see that the Holy Spirit will not abandon you and the Holy Spirit will not leave you.
> 
> Anxiety will lift, depression will lift, confusion will lift, clarity will come, closeness to the Holy Spirit will come, not because you're running from those questions, but because you're bringing them to the light and you're bringing them to him. And he will not shame you for them. He will strengthen you right through in the midst of those questions in Jesus' name.

### v3 proposition (50 words)

The author encourages people to bring their questions and pain to God, and to trust that he will provide comfort, strength, and guidance, and that he will not shame or abandon them, but will instead walk with them through their struggles and provide clarity and closeness to the Holy Spirit.

### v4 proposition(s) — same document, 7 total v4 propositions produced

**v4 #1** (86 words):

Vlad Savchuk invites people to write down their three things, to connect with the right people, and to bring people to the right place, and he encourages those who are struggling with painful questions to raise their hands and ask the Holy Spirit to touch them, and to put their hand on their heart and say, 'Holy Spirit, walk with me through this, help me through this,' and he prays that the Holy Spirit will cover them with the blanket of His love, mercy, and grace.

---

## Sample 19/20 — Carter Conlon

**Sermon:** Your Time of Freedom Has Come by Carter Conlon  
**URL:** https://www.youtube.com/watch?v=qOgN-puCIJU

### SOURCE CHUNK (chunk_index=1)

> evening, and you've been captivated by drugs or loneliness or depression or illness or heartache. Whatever your situation is, you've been captivated as long as you can remember, and you're now listening. You've come to this prayer meeting, and now you're hearing a voice that's telling you this evening, and I'm telling you with authority that your time of freedom has come.
> 
> You can get up, and you can get out. There is victory for you. So in your heart, you probably are saying, "Why should I believe this speaker tonight? Why should I believe the songs that have been sung on this platform this evening? Why should I believe the testimonies that have been shared, the prayers that have been prayed? Why should I believe that it will make any difference in my life?"
> 
> Let's go back to the beginning where Moses, in Exodus chapter 3, God comes to Moses in the wilderness. He knew he had been called at one time to do a great work for the kingdom of God, but he felt no doubt that he had lost the opportunity. He had been impulsive. He had a bad temper, and he'd let it get a hold of him. And because of it, he had to flee into a foreign place.
> 
> And he found himself not just only in the desert, but the scripture says in the backside of the desert. It doesn't get any worse. It was like as far into the desert probably as you can go. But it's there where God met this man. And the Lord said in Exodus 3:7, "I've surely seen the oppression of my people who are in Egypt, and I've heard their cry because of their taskmasters."
> 
> In other words, because of their slavery and what they were forced to do every day. I've heard their cries. Realistically, it had to be an all-day cry. I know that I'm speaking to somebody today that your cry is not just at night or not just in the morning. It's morning till night. You cry. God, I can't take this anymore.
> 
> As one of our prayer requests tonight that came in, just help me. Or I don't remember exactly how it was worded, but it was God, you know what I need. And the Lord said, "I've heard their cry for their because of their cry for their because of their cry for their taskmasters, for I know their sorrows. So I've come down to deliver them out of the hand of the Egyptians and to bring them up from that land to a good and a large land, a land flowing with milk and honey."

### v3 proposition (48 words)

The author asserts that God speaks to individuals, telling them that their time of freedom has come, just as he told Moses in Exodus 3, and that he will take them out of their current situation and into a new place, driving out obstacles and giving them victory.

### v4 proposition(s) — same document, 5 total v4 propositions produced

**v4 #1** (77 words):

Carter Conlon teaches that the people of God in Moses' time believed two old men, Moses and Aaron, who told them that their time of freedom had come, despite being in captivity for hundreds of years, because God had given them signs to prove His power and presence, as seen in Exodus 3:7 where God says, 'I've surely seen the oppression of my people who are in Egypt, and I've heard their cry because of their taskmasters.'

---

## Sample 20/20 — Carter Conlon

**Sermon:** The Faithfulness of My Father’s Hand by Carter Conlon  
**URL:** https://www.youtube.com/watch?v=7JqjCkU7QV8

### SOURCE CHUNK (chunk_index=3)

> . True Christianity, the purest expression of the Christian faith is found in living not for ourselves but for the benefit of others. Yielding our lives for the sake of somebody else. Somebody else who's in a prison. Somebody else who's blinded. Somebody else who's wounded in heart. Somebody else who has no future. They have no hope. If somebody doesn't fight for them. 
> 
> If somebody doesn't stand up for them. If somebody doesn't stand up and pray for them. If somebody doesn't go to them with a word from God. We can't do everything. Obviously, my father couldn't defeat the German army on his own, but he could do something. And that's got to be the attitude of heart in the house of God and among those who are called by the name of Jesus Christ. 
> 
> In the book of Proverbs Proverbs chapter 8. Now, it's it's about wisdom solely, this particular chapter. It's not really about Christ. Some believe it is, but I I personally don't. I think it's really about wisdom that dwelt with God from the from before even time began. 
> 
> But in this passage of scripture in Proverbs 8, we get a picture of what the fellowship between God the Father and God the Son must have been like before time began, before the world was created. So I want to look at Proverbs 8 just for a moment from verse 22 to verse 30 as a type. It's only a picture. It's it's not necessarily about Christ himself, but it's a picture. 
> 
> The Lord possessed me at the beginning of his way, before his works of old. I have been established from everlasting, from the beginning. Before there was ever an earth, when there were no depths, I was brought forth. When there were no fountains abounding with water, before the mountains were settled, before the hills, I was brought forth. 
> 
> While at yet he had not made the earth or the fields or the primal dust of the world, when he prepared the heavens, I was there. When he drew a circle on the face of the deep, when he established the clouds above, when he strengthened the fountains of the deep, when he assigned to the sea its limit so that the waters would not transgress his command, when he marked out the foundations of the earth, then I was beside him as a master craftsman, and I was daily his delight, rejoicing always before him.

### v3 proposition (46 words)

The author teaches that true Christianity is found in living not for oneself, but for the benefit of others, and that this is demonstrated through yielding one's life for the sake of someone else, as seen in the example of the author's father and Jesus Christ.

### v4 proposition(s) — same document, 4 total v4 propositions produced

**v4 #1** (104 words):

According to Carter Conlon, true Christianity is found in living not for oneself, but for the benefit of others, yielding one's life for the sake of somebody else, and that this is exemplified in the life of Jesus Christ, who did not consider it robbery to be equal with God, but made himself of no reputation and took on the form of a bond servant, as stated in Philippians chapter 2, and that Conlon's father, who volunteered to fight in a war and gave up his dream of becoming an engineer or architect, demonstrated a similar selflessness and character, which Conlon strives to emulate.

---

## Stats

**v4 word count distribution across the full run** (all 115 propositions produced across all 18 documents):
- min: 40
- median: 60
- max: 124

(For comparison, v3's distribution across the full 2,488-row corpus, from the earlier audit: min=17, p10=30, median=40, p90=54, max=182.)

**Propositions produced per document, v3 (full existing DB count) vs v4 (this run):**

| Document | Speaker | v3 count | v4 count | chunks |
|---|---|---|---|---|
| Two Words by Leonard Ravenhill | Leonard Ravenhill | 6 | 4 | 1 |
| Cost Of Discipleship by Leonard Ravenhill - Part 1 | Leonard Ravenhill | 6 | 4 | 4 |
| Finding True Joy: The Danger of Entertainment by Leonard Ravenhill #shorts | Leonard Ravenhill | 4 | 2 | 1 |
| "Forget Miricales Preach Holiness" by Leonard Ravenhill | Leonard Ravenhill | 5 | 3 | 1 |
| God's Glory by Leonard Ravenhill | Leonard Ravenhill | 10 | 9 | 15 |
| (Compilation) A Cry for Revival by Leonard Ravenhill | Leonard Ravenhill | 12 | 14 | 6 |
| The Spirit of a Prophet Leonard Ravenhill | Leonard Ravenhill | 9 | 5 | 4 |
| Sixteen Lessons I Have Learnt - Part 2 by Zac Poonen | Zac Poonen | 20 | 19 | 17 |
| What It Means to Be a Disciple of Jesus by Zac Poonen | Zac Poonen | 7 | 5 | 19 |
| Sermon on the Mount - Part 9 by Zac Poonen | Zac Poonen | 10 | 8 | 30 |
| Be Content with the Way God Made You by Zac Poonen | Zac Poonen | 10 | 7 | 23 |
| This is the Price of Being Used by God (Few Pay It) | Vlad Savchuk | 10 | 5 | 33 |
| This Is What Anger Does to You | Vlad Savchuk | 9 | 5 | 10 |
| How to Win the War on Porn | Your Porn Battle Plan | Vlad Savchuk | 8 | 4 | 13 |
| Satan is Using Your Phone Against You – Here’s How! | Vlad Savchuk | 13 | 5 | 6 |
| The Questions Jesus ACTUALLY Wants You to Ask Him | Vlad Savchuk | 7 | 7 | 15 |
| Your Time of Freedom Has Come by Carter Conlon | Carter Conlon | 6 | 5 | 13 |
| The Faithfulness of My Father’s Hand by Carter Conlon | Carter Conlon | 8 | 4 | 14 |

**Documents where v4 produced noticeably fewer or more propositions than v3:**

- The Spirit of a Prophet Leonard Ravenhill (Leonard Ravenhill): v3=9, v4=5 (FEWER by 4)
- Be Content with the Way God Made You by Zac Poonen (Zac Poonen): v3=10, v4=7 (FEWER by 3)
- This is the Price of Being Used by God (Few Pay It) (Vlad Savchuk): v3=10, v4=5 (FEWER by 5)
- This Is What Anger Does to You (Vlad Savchuk): v3=9, v4=5 (FEWER by 4)
- How to Win the War on Porn | Your Porn Battle Plan (Vlad Savchuk): v3=8, v4=4 (FEWER by 4)
- Satan is Using Your Phone Against You – Here’s How! (Vlad Savchuk): v3=13, v4=5 (FEWER by 8)
- The Faithfulness of My Father’s Hand by Carter Conlon (Carter Conlon): v3=8, v4=4 (FEWER by 4)

**Token cost of the v4 run:**
- 135111 prompt tokens + 11364 completion tokens = **146475 total**
- 19 Groq calls (18 documents + 1 retry -- one call hit a JSON parse error unrelated to length/truncation and was retried once, succeeding immediately; 6111 tokens of the total are that retry)

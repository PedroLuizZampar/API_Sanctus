PROMPT_EVANGELHO = """
  Atue como um Diretor Espiritual e Teólogo Católico de profunda sensibilidade pastoral. Quero que você crie uma reflexão litúrgica diária baseada no Evangelho do dia. O texto deve ser estritamente devocional, com sólida teologia, mas escrito de forma natural, acolhedora e de fácil compreensão para o fiel leigo. 

Não insira o texto do Evangelho por extenso, concentre-se exclusivamente na meditação profunda sobre ele. Não responda como um modelo de IA; comece diretamente no conteúdo, sem saudações or introduções formais.

A estrutura geral de títulos (H2 e H3) e o uso de negritos devem seguir rigorosamente o modelo abaixo, mas a organização interna do conteúdo (seja por parágrafos fluídos, listas ou blocos de citação, apenas tabelas que não) fica totalmente a seu critério, utilizando o formato que você considerar mais didático e profundo para o tema do dia.

## Contextualização Litúrgica
Crie uma introdução situando o leitor na liturgia de hoje. Use a fórmula básica: "Como hoje é [Dia da Semana], [Data por extenso], a Igreja celebra a [Semana e Tempo Litúrgico]. A liturgia de hoje nos convida a...". Faça uma ponte direta entre o tempo litúrgico e o tema central do Evangelho, preparando a alma do leitor.

---

## A Mensagem do Dia: [Subtítulo Curto e Impactante]
Desenvolva a mensagem central do Evangelho. Você deve abordar o contexto teológico (o que Jesus quis ensinar originalmente naquele momento histórico, indo além da superfície) e a conexão com o agora (como esse ensinamento desafia o homem moderno, o ritmo de vida atual, as redes sociais ou a cultura contemporânea). Sinta-se livre para organizar esses dois aspectos em parágrafos, tópicos ou citações, focando na profundidade e na clareza.

---

## O Ensinamento Prático de Jesus: A Radicalidade do Evangelho
Apresente os desdobramentos práticos e as virtudes extraídas da passagem. Esta seção deve conter ensinamentos essenciais e passos concretos para o fiel aplicar no cotidiano, além de perguntas reflexivas para o exame de consciência. A organização visual desta seção é livre: você pode usar tabelas comparativas, listas ordenadas ou blocos de texto, desde que use negritos nos conceitos-chave para guiar o olhar do leitor.

---

## Oração Acerca do Tema
Comece com: "Em nome do Pai, do Filho e do Espírito Santo. Amém."
Escreva uma oração íntima, sincera e profunda em primeira pessoa do singular (eu). A oração deve passar naturalmente por momentos de reconhecimento da soberania divina, pedido de perdão pelas fraquezas diárias, súplica por força para realizar as renúncias necessárias na vida moderna e intercessão pelas famílias ou pela Igreja. Termine com "Amém."

---

## Gere a meditação para o Evangelho de hoje:
"""

PROMPT_CURIOSIDADES = """
  Atue como um Professor de História da Igreja e Catequista dinâmico. Quero que você crie um texto fascinante, rico em conteúdo e altamente visual sobre o seguinte assunto da fé católica: **{tema}**.

O tom deve ser natural, instigante, que desperte curiosidade no leitor, mantendo a profundidade e a reverência teológica. Não responda como um modelo de IA; comece diretamente no texto.

A estrutura de títulos (H2 e H3) e o uso de negritos devem seguir rigorosamente o modelo abaixo, mas a organização interna do conteúdo (o uso de listas, parágrafos ou blocos de destaque, apenas tabelas que não) fica totalmente a seu critério, utilizando o formato que você considerar mais didático e atraente para o assunto escolhido.

## Mistérios da Fé: [Nome do Assunto Geral]
Abra com uma pergunta provocativa para capturar o leitor e faça uma breve introdução contextualizando como a mentalidade católica sempre utilizou a arte, a história e os símbolos como uma catequese viva. Termine esta introdução com a frase: "Aqui está o resumo rápido para você dominar o assunto hoje:"

---

## O que é (ou o que foram) os [Nome do Assunto]?
Desenvolva a definição técnica, histórica ou conceitual do assunto. Explique a origem desse fato ou tradição e mostre que o objetivo nunca foi puramente estético ou social, mas sim uma chave de leitura para realidades espirituais invisíveis. Organize a explicação da maneira que achar mais clara.

---

## Três Pilares Surpreendentes deste Legado
Apresente exatamente 3 pontos fundamentais sobre o tema. Para cada um dos 3 pontos, você deve criar um subtítulo H3 indicando o nome do item. A forma de expor o fato histórico e o significado espiritual de cada item é livre (em parágrafos separados, listas ou blocos), mas você deve obrigatoriamente usar o termo **O significado:** em negrito para destacar a explicação teológica e sua conexão com a vida de fé.

### [Nome do Primeiro Item]
### [Nome do Segundo Item]
### [Nome do Terceiro Item]

---

## Por que isso importa hoje?
Escreva uma conclusão profunda e de fácil compreensão, consolidando o aprendizado. Mostre como o olhar sacramental da Igreja une o mundo visível ao invisível, e como resgatar esse conhecimento enriquece a nossa experiência de fé no mundo contemporâneo.

---

Gere o texto seguindo rigorosamente o tema fornecido (**{tema}**) e o modelo de estrutura acima.
"""

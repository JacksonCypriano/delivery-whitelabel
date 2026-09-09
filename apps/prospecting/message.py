def build_prospecting_message(establishment: str) -> str:
    name = " ".join((establishment or "").split()).strip()
    if not name:
        name = "seu estabelecimento"
        first_reference = "o seu estabelecimento"
        second_reference = "seu estabelecimento"
    else:
        first_reference = f"a {name}"
        second_reference = f"a {name}"

    return (
        "Olá! Tudo bem? Meu nome é Jackson Cypriano, sou fundador do VemDeDelivery.\n\n"
        f"Criamos uma solução para {first_reference} ter um site próprio, personalizado com a identidade do estabelecimento, "
        "onde o cliente consulta produtos, fotos, preços e adicionais, monta o pedido e envia tudo organizado para o WhatsApp da loja.\n\n"
        "Assim, vocês continuam atendendo pelo WhatsApp, mas recebem o pedido praticamente pronto, com menos perguntas repetidas "
        "e menos risco de anotar algum item incorretamente.\n\n"
        f"Se tiver interesse em conhecer melhor o VemDeDelivery e ver como ele pode funcionar para {second_reference}, "
        "responda a esta mensagem e eu envio uma apresentação com todos os recursos, condições e o acesso à nossa loja demonstrativa "
        "para vocês testarem diretamente pelo celular.\n\n"
        "Jackson Cypriano\n"
        "Fundador do VemDeDelivery\n"
        "COBRADEV SOLUTIONS\n"
        "CNPJ 59.198.345/0001-44\n\n"
        "Caso este número não pertença mais ao estabelecimento, peço desculpas pelo contato e, por favor, desconsidere esta mensagem."
    )

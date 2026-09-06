# Hotfix — primeiro acesso e teste de data

Corrige duas causas independentes encontradas na suíte crítica:

1. Senha temporária contendo `&` era HTML-escapada como `&amp;` no e-mail de texto puro, fazendo o login de primeiro acesso falhar de forma aleatória.
2. O teste do campo de nascimento consultava `widget.attrs["type"]`, mas o Django armazena o tipo efetivo de widgets `Input` em `widget.input_type`.

Também adiciona um teste determinístico com senha contendo `&`.

Não altera banco, assets, layout, Asaas ou ViaCEP.

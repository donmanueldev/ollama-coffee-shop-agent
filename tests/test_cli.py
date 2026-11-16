from coffee_agent import StreamedReply


def test_streamed_reply_opens_the_barista_line_on_first_text(capsys):
    reply = StreamedReply()
    reply.end()  # nothing streamed yet: no empty "Barista:" line
    reply("Hola, ")
    reply("¿qué café quieres?")
    reply.end("Hola, ¿qué café quieres?")

    assert capsys.readouterr().err == "Barista: Hola, ¿qué café quieres?\n\n"


def test_streamed_reply_prints_answers_that_were_not_streamed(capsys):
    reply = StreamedReply()
    reply.end("Perdón, me enredé con tu solicitud.")

    assert capsys.readouterr().err == "Barista: Perdón, me enredé con tu solicitud.\n\n"

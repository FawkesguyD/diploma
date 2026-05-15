# RabbitMQ + community плагин rabbitmq_delayed_message_exchange.
# Версия плагина должна совпадать с минорной версией RabbitMQ.
FROM rabbitmq:3.13-management

ARG DELAYED_PLUGIN_VERSION=3.13.0
ADD --chown=rabbitmq:rabbitmq \
    https://github.com/rabbitmq/rabbitmq-delayed-message-exchange/releases/download/v${DELAYED_PLUGIN_VERSION}/rabbitmq_delayed_message_exchange-${DELAYED_PLUGIN_VERSION}.ez \
    /opt/rabbitmq/plugins/rabbitmq_delayed_message_exchange-${DELAYED_PLUGIN_VERSION}.ez

COPY enabled_plugins  /etc/rabbitmq/enabled_plugins
COPY rabbitmq.conf    /etc/rabbitmq/rabbitmq.conf
COPY definitions.json /etc/rabbitmq/definitions.json

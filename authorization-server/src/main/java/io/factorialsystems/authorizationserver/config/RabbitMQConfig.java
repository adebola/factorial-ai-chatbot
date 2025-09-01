package io.factorialsystems.authorizationserver.config;

import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitMQConfig {

//    @Value("${rabbitmq.queue.audit.name}")
//    private String auditQueueName;
//
//    @Value("${rabbitmq.queue.mail.name}")
//    private String mailQueueName;

    @Value("${authorization.config.rabbitmq.exchange.name}")
    private String exchange;

//    @Value("${rabbitmq.routing.audit.key}")
//    private String auditRouting;
//
//    @Value("${rabbitmq.routing.mail.key}")
//    private String mailRouting;

//    @Bean
//    public Queue auditQueue() {
//        return new Queue(auditQueueName);
//    }
//
//    @Bean
//    public Queue mailQueue() {
//        return new Queue(mailQueueName);
//    }

    @Bean
    public TopicExchange exchange() {
        return new TopicExchange(exchange);
    }

//    @Bean
//    public Binding auditBinding(TopicExchange exchange) {
//        return BindingBuilder
//                .bind(auditQueue())
//                .to(exchange)
//                .with(auditRouting);
//    }
//
//    @Bean
//    public Binding mailBinding(TopicExchange exchange) {
//        return BindingBuilder
//                .bind(mailQueue())
//                .to(exchange)
//                .with(mailRouting);
//    }

    @Bean
    public MessageConverter converter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    public AmqpTemplate amqpTemplate(ConnectionFactory connectionFactory, MessageConverter converter) {
        RabbitTemplate rabbitTemplate = new RabbitTemplate(connectionFactory);
        rabbitTemplate.setMessageConverter(converter);
        return rabbitTemplate;
    }
}

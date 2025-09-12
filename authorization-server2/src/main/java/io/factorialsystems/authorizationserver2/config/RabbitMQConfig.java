package io.factorialsystems.authorizationserver2.config;

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
    @Value("${authorization.config.rabbitmq.queue.widget}")
    private String widgetQueueName;
    
    @Value("${authorization.config.rabbitmq.queue.plan-update:plan-update-queue}")
    private String planUpdateQueueName;
    
    @Value("${authorization.config.rabbitmq.queue.logo-update:logo-update-queue}")
    private String logoUpdateQueueName;

    @Value("${authorization.config.rabbitmq.key.widget}")
    private String widgetRouting;
    
    @Value("${authorization.config.rabbitmq.key.plan-update:plan.update}")
    private String planUpdateRouting;
    
    @Value("${authorization.config.rabbitmq.key.logo-update:logo.update}")
    private String logoUpdateRouting;

    @Value("${authorization.config.rabbitmq.exchange.name}")
    private String exchange;

    @Bean
    public Queue widgetQueue() {
        return new Queue(widgetQueueName);
    }
    
    @Bean
    public Queue planUpdateQueue() {
        return new Queue(planUpdateQueueName, true); // durable = true
    }
    
    @Bean
    public Queue logoUpdateQueue() {
        return new Queue(logoUpdateQueueName, true); // durable = true
    }

    @Bean
    public TopicExchange exchange() {
        return new TopicExchange(exchange);
    }

    @Bean
    public Binding widgettBinding(TopicExchange exchange) {
        return BindingBuilder
                .bind(widgetQueue())
                .to(exchange)
                .with(widgetRouting);
    }
    
    @Bean
    public Binding planUpdateBinding(TopicExchange exchange) {
        return BindingBuilder
                .bind(planUpdateQueue())
                .to(exchange)
                .with(planUpdateRouting);
    }
    
    @Bean
    public Binding logoUpdateBinding(TopicExchange exchange) {
        return BindingBuilder
                .bind(logoUpdateQueue())
                .to(exchange)
                .with(logoUpdateRouting);
    }


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

package io.factorialsystems.authorizationserver2.mapper;

import io.factorialsystems.authorizationserver2.model.RegisteredClient;
import org.apache.ibatis.annotations.*;

import java.util.List;

@Mapper
public interface RegisteredClientMapper {
    
    @Select("SELECT * FROM registered_clients WHERE client_id = #{clientId} AND is_active = true")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "clientId", column = "client_id"),
        @Result(property = "clientSecret", column = "client_secret"),
        @Result(property = "clientName", column = "client_name"),
        @Result(property = "clientAuthenticationMethods", column = "client_authentication_methods"),
        @Result(property = "authorizationGrantTypes", column = "authorization_grant_types"),
        @Result(property = "redirectUris", column = "redirect_uris"),
        @Result(property = "postLogoutRedirectUris", column = "post_logout_redirect_uris"),
        @Result(property = "scopes", column = "scopes"),
        @Result(property = "clientSettings", column = "client_settings"),
        @Result(property = "tokenSettings", column = "token_settings"),
        @Result(property = "requireAuthorizationConsent", column = "require_authorization_consent"),
        @Result(property = "requireProofKey", column = "require_proof_key"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    RegisteredClient findByClientId(@Param("clientId") String clientId);
    
    @Select("SELECT * FROM registered_clients WHERE id = #{id}")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "clientId", column = "client_id"),
        @Result(property = "clientSecret", column = "client_secret"),
        @Result(property = "clientName", column = "client_name"),
        @Result(property = "clientAuthenticationMethods", column = "client_authentication_methods"),
        @Result(property = "authorizationGrantTypes", column = "authorization_grant_types"),
        @Result(property = "redirectUris", column = "redirect_uris"),
        @Result(property = "postLogoutRedirectUris", column = "post_logout_redirect_uris"),
        @Result(property = "scopes", column = "scopes"),
        @Result(property = "clientSettings", column = "client_settings"),
        @Result(property = "tokenSettings", column = "token_settings"),
        @Result(property = "requireAuthorizationConsent", column = "require_authorization_consent"),
        @Result(property = "requireProofKey", column = "require_proof_key"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    RegisteredClient findById(@Param("id") String id);
    
    @Select("SELECT * FROM registered_clients WHERE is_active = true")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "clientId", column = "client_id"),
        @Result(property = "clientSecret", column = "client_secret"),
        @Result(property = "clientName", column = "client_name"),
        @Result(property = "clientAuthenticationMethods", column = "client_authentication_methods"),
        @Result(property = "authorizationGrantTypes", column = "authorization_grant_types"),
        @Result(property = "redirectUris", column = "redirect_uris"),
        @Result(property = "postLogoutRedirectUris", column = "post_logout_redirect_uris"),
        @Result(property = "scopes", column = "scopes"),
        @Result(property = "clientSettings", column = "client_settings"),
        @Result(property = "tokenSettings", column = "token_settings"),
        @Result(property = "requireAuthorizationConsent", column = "require_authorization_consent"),
        @Result(property = "requireProofKey", column = "require_proof_key"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<RegisteredClient> findAllActive();
    
    @Insert("INSERT INTO registered_clients (id, client_id, client_secret, client_name, " +
            "client_authentication_methods, authorization_grant_types, redirect_uris, post_logout_redirect_uris, " +
            "scopes, client_settings, token_settings, require_authorization_consent, require_proof_key, " +
            "is_active, created_at, updated_at) " +
            "VALUES (#{id}, #{clientId}, #{clientSecret}, #{clientName}, " +
            "#{clientAuthenticationMethods}, #{authorizationGrantTypes}, #{redirectUris}, #{postLogoutRedirectUris}, " +
            "#{scopes}, #{clientSettings}, #{tokenSettings}, #{requireAuthorizationConsent}, #{requireProofKey}, " +
            "#{isActive}, #{createdAt}, #{updatedAt})")
    int insert(RegisteredClient registeredClient);
    
    @Update("UPDATE registered_clients SET client_secret = #{clientSecret}, client_name = #{clientName}, " +
            "client_authentication_methods = #{clientAuthenticationMethods}, " +
            "authorization_grant_types = #{authorizationGrantTypes}, redirect_uris = #{redirectUris}, " +
            "post_logout_redirect_uris = #{postLogoutRedirectUris}, scopes = #{scopes}, " +
            "client_settings = #{clientSettings}, token_settings = #{tokenSettings}, " +
            "require_authorization_consent = #{requireAuthorizationConsent}, " +
            "require_proof_key = #{requireProofKey}, is_active = #{isActive}, updated_at = #{updatedAt} " +
            "WHERE id = #{id}")
    int update(RegisteredClient registeredClient);
    
    @Delete("DELETE FROM registered_clients WHERE id = #{id}")
    int deleteById(@Param("id") String id);
}
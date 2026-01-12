package io.factorialsystems.authorizationserver2.mapper;

import io.factorialsystems.authorizationserver2.model.VerificationToken;
import org.apache.ibatis.annotations.*;

import java.time.OffsetDateTime;
import java.util.List;

@Mapper
public interface VerificationTokenMapper {

    @Insert("""
        INSERT INTO verification_tokens (
            id, token, user_id, email, token_type, expires_at, created_at, updated_at
        ) VALUES (
            #{id}, #{token}, #{userId}, #{email}, #{tokenType}, #{expiresAt}, #{createdAt}, #{updatedAt}
        )
        """)
    int insert(VerificationToken verificationToken);

    @Select("""
        SELECT id, token, user_id, email, token_type, expires_at, used_at, created_at, updated_at
        FROM verification_tokens
        WHERE token = #{token}
        """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "token", column = "token"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "email", column = "email"),
        @Result(property = "tokenType", column = "token_type"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "usedAt", column = "used_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    VerificationToken findByToken(@Param("token") String token);

    @Select("""
        SELECT id, token, user_id, email, token_type, expires_at, used_at, created_at, updated_at
        FROM verification_tokens
        WHERE user_id = #{userId} AND token_type = #{tokenType}
        ORDER BY created_at DESC
        """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "token", column = "token"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "email", column = "email"),
        @Result(property = "tokenType", column = "token_type"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "usedAt", column = "used_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<VerificationToken> findByUserIdAndType(@Param("userId") String userId, @Param("tokenType") VerificationToken.TokenType tokenType);

    @Update("""
        UPDATE verification_tokens
        SET used_at = #{usedAt}, updated_at = #{updatedAt}
        WHERE id = #{id}
        """)
    int markAsUsed(VerificationToken verificationToken);

    @Update("""
        UPDATE verification_tokens
        SET used_at = #{usedAt}, updated_at = #{updatedAt}
        WHERE token = #{token}
        """)
    int markAsUsedByToken(@Param("token") String token, @Param("usedAt") OffsetDateTime usedAt, @Param("updatedAt") OffsetDateTime updatedAt);

    @Delete("""
        DELETE FROM verification_tokens
        WHERE expires_at < #{expirationTime}
        """)
    int deleteExpiredTokens(@Param("expirationTime") OffsetDateTime expirationTime);

    @Delete("""
        DELETE FROM verification_tokens
        WHERE user_id = #{userId} AND token_type = #{tokenType}
        """)
    int deleteByUserIdAndType(@Param("userId") String userId, @Param("tokenType") VerificationToken.TokenType tokenType);

    @Select("""
        SELECT id, token, user_id, email, token_type, expires_at, used_at, created_at, updated_at
        FROM verification_tokens
        WHERE email = #{email} AND token_type = #{tokenType}
        ORDER BY created_at DESC
        """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "token", column = "token"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "email", column = "email"),
        @Result(property = "tokenType", column = "token_type"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "usedAt", column = "used_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<VerificationToken> findByEmailAndType(@Param("email") String email, @Param("tokenType") VerificationToken.TokenType tokenType);

    @Select("""
        SELECT COUNT(*)
        FROM verification_tokens
        WHERE user_id = #{userId} AND token_type = #{tokenType} AND created_at > #{sinceTime}
        """)
    int countRecentTokensByUser(@Param("userId") String userId, @Param("tokenType") VerificationToken.TokenType tokenType, @Param("sinceTime") OffsetDateTime sinceTime);

    @Select("""
        SELECT COUNT(*)
        FROM verification_tokens
        WHERE email = #{email} AND token_type = #{tokenType} AND created_at > #{sinceTime}
        """)
    int countRecentTokensByEmail(@Param("email") String email, @Param("tokenType") VerificationToken.TokenType tokenType, @Param("sinceTime") OffsetDateTime sinceTime);

    @Delete("""
        DELETE FROM verification_tokens
        WHERE email = #{email} AND token_type = #{tokenType}
        """)
    int deleteByEmailAndType(@Param("email") String email, @Param("tokenType") VerificationToken.TokenType tokenType);
}
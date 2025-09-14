package io.factorialsystems.authorizationserver.typehandler;

import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;
import org.apache.ibatis.type.MappedJdbcTypes;
import org.apache.ibatis.type.MappedTypes;

import java.sql.*;
import java.util.ArrayList;
import java.util.List;

/**
 * MyBatis type handler for PostgreSQL TEXT[] arrays.
 * Converts between Java List<String> and PostgreSQL text arrays.
 */
@MappedTypes(List.class)
@MappedJdbcTypes(JdbcType.ARRAY)
public class StringArrayTypeHandler extends BaseTypeHandler<List<String>> {

    @Override
    public void setNonNullParameter(PreparedStatement ps, int i, List<String> parameter, JdbcType jdbcType) throws SQLException {
        if (parameter == null || parameter.isEmpty()) {
            ps.setArray(i, null);
        } else {
            // Convert List<String> to PostgreSQL text array
            Array array = ps.getConnection().createArrayOf("text", parameter.toArray(new String[0]));
            ps.setArray(i, array);
        }
    }

    @Override
    public List<String> getNullableResult(ResultSet rs, String columnName) throws SQLException {
        Array array = rs.getArray(columnName);
        return extractArray(array);
    }

    @Override
    public List<String> getNullableResult(ResultSet rs, int columnIndex) throws SQLException {
        Array array = rs.getArray(columnIndex);
        return extractArray(array);
    }

    @Override
    public List<String> getNullableResult(CallableStatement cs, int columnIndex) throws SQLException {
        Array array = cs.getArray(columnIndex);
        return extractArray(array);
    }

    /**
     * Extract string list from SQL Array
     */
    private List<String> extractArray(Array array) throws SQLException {
        if (array == null) {
            return new ArrayList<>();
        }

        try {
            Object[] objectArray = (Object[]) array.getArray();
            if (objectArray == null) {
                return new ArrayList<>();
            }

            List<String> result = new ArrayList<>(objectArray.length);
            for (Object obj : objectArray) {
                if (obj != null) {
                    result.add(obj.toString());
                }
            }
            return result;
        } finally {
            array.free();
        }
    }
}
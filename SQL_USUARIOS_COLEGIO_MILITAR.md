# SQL Usuarios Colegio Militar

Este documento crea la tabla dedicada para acceso interno de empleados al módulo `IA León`.

Nombre propuesto de la tabla:

- `colegio_militarizado_users`

Razón:
- evita mezclar estos accesos con la tabla genérica `users` del admin actual
- permite manejar roles, planteles y cambio forzoso de contraseña
- deja base limpia para el portal docente

## 1. Habilitar `pgcrypto`

Se usa para generar hashes bcrypt dentro de PostgreSQL.

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

## 2. Crear tabla

```sql
CREATE TABLE IF NOT EXISTS colegio_militarizado_users (
  id SERIAL PRIMARY KEY,
  area TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  responsable TEXT,
  alias TEXT,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'staff',
  campus TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  last_login_at TIMESTAMP
);
```

## 3. Regla de clasificación sugerida

- `admin`: cuenta maestra
- `director`: direcciones generales o de plantel
- `academic_coordination`: coordinaciones académicas
- `administrative_coordination`: coordinaciones administrativas
- `staff`: resto del personal

## 4. Cargar usuarios iniciales

Este bloque inserta todos los correos de `CORREOS.MD`.

Importante:
- las contraseñas quedan hasheadas con bcrypt
- `must_change_password = TRUE` para forzar cambio en el primer acceso
- `alias` se guarda como `NULL` cuando en el archivo aparece `—`

```sql
INSERT INTO colegio_militarizado_users (
  area, email, responsable, alias, password_hash, role, campus, is_active, must_change_password
) VALUES
  ('Cuenta Maestra', 'admin@colegiomilitarizadonl.com', 'Administración', 'admin@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'admin', NULL, TRUE, TRUE),
  ('Recepción', 'recepcion@colegiomilitarizadonl.com', 'Pendiente', 'info@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'staff', NULL, TRUE, TRUE),
  ('Dirección General', 'direccion.general@colegiomilitarizadonl.com', 'Director General', 'director@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', NULL, TRUE, TRUE),
  ('Secretaría de Dirección', 'secretaria@colegiomilitarizadonl.com', 'Secretaria de Dirección', 'asistente@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'staff', NULL, TRUE, TRUE),
  ('Dirección Administrativa', 'administracion@colegiomilitarizadonl.com', 'Director Administrativo', 'admin@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', NULL, TRUE, TRUE),
  ('Secretaría de Administración', 'secretaria.administracion@colegiomilitarizadonl.com', 'Secretaria Administrativa', NULL, crypt('CMNL2026!Temp#', gen_salt('bf')), 'staff', NULL, TRUE, TRUE),
  ('Jurídico', 'juridico@colegiomilitarizadonl.com', 'Director Jurídico', 'legal@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', NULL, TRUE, TRUE),
  ('Dirección Académica', 'academico@colegiomilitarizadonl.com', 'Director Académico', 'direccion.academica@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', NULL, TRUE, TRUE),
  ('Dirección de Cuerpo de Alumnos', 'cuerpo.alumnos@colegiomilitarizadonl.com', 'Director de Cuerpo de Alumnos', 'disciplina@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', NULL, TRUE, TRUE),
  ('Recursos Humanos', 'recursos.humanos@colegiomilitarizadonl.com', 'Director de Recursos Humanos', 'recursoshumanos@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', NULL, TRUE, TRUE),
  ('Dirección de Vinculación', 'vinculacion@colegiomilitarizadonl.com', 'Director de Vinculación', 'relaciones@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', NULL, TRUE, TRUE),
  ('Dirección de Planeación', 'planeacion@colegiomilitarizadonl.com', 'Director de Planeación', 'estrategia@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', NULL, TRUE, TRUE),

  ('Dirección Plantel Monterrey', 'direccion.monterrey@colegiomilitarizadonl.com', 'Director Plantel Monterrey', 'plantel.monterrey@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'Monterrey', TRUE, TRUE),
  ('Coordinación Administrativa Plantel Monterrey', 'administracion.monterrey@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.monterrey@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'Monterrey', TRUE, TRUE),
  ('Coordinación Académica Plantel Monterrey', 'academico.monterrey@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.monterrey@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'Monterrey', TRUE, TRUE),

  ('Dirección Plantel San Nicolás', 'direccion.sannicolas@colegiomilitarizadonl.com', 'Director Plantel San Nicolás', 'plantel.sannicolas@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'San Nicolás', TRUE, TRUE),
  ('Coordinación Administrativa Plantel San Nicolás', 'administracion.sannicolas@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.sannicolas@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'San Nicolás', TRUE, TRUE),
  ('Coordinación Académica Plantel San Nicolás', 'academico.sannicolas@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.sannicolas@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'San Nicolás', TRUE, TRUE),

  ('Dirección Plantel Montemorelos', 'direccion.montemorelos@colegiomilitarizadonl.com', 'Director Plantel Montemorelos', 'plantel.montemorelos@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'Montemorelos', TRUE, TRUE),
  ('Coordinación Administrativa Plantel Montemorelos', 'administracion.montemorelos@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.montemorelos@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'Montemorelos', TRUE, TRUE),
  ('Coordinación Académica Plantel Montemorelos', 'academico.montemorelos@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.montemorelos@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'Montemorelos', TRUE, TRUE),

  ('Dirección Plantel Apodaca', 'direccion.apodaca@colegiomilitarizadonl.com', 'Director Plantel Apodaca', 'plantel.apodaca@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'Apodaca', TRUE, TRUE),
  ('Coordinación Administrativa Plantel Apodaca', 'administracion.apodaca@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.apodaca@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'Apodaca', TRUE, TRUE),
  ('Coordinación Académica Plantel Apodaca', 'academico.apodaca@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.apodaca@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'Apodaca', TRUE, TRUE),

  ('Dirección Plantel García', 'direccion.garcia@colegiomilitarizadonl.com', 'Director Plantel García', 'plantel.garcia@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'García', TRUE, TRUE),
  ('Coordinación Administrativa Plantel García', 'administracion.garcia@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.garcia@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'García', TRUE, TRUE),
  ('Coordinación Académica Plantel García', 'academico.garcia@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.garcia@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'García', TRUE, TRUE),

  ('Dirección Plantel Escobedo', 'direccion.escobedo@colegiomilitarizadonl.com', 'Director Plantel Escobedo', 'plantel.escobedo@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'Escobedo', TRUE, TRUE),
  ('Coordinación Administrativa Plantel Escobedo', 'administracion.escobedo@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.escobedo@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'Escobedo', TRUE, TRUE),
  ('Coordinación Académica Plantel Escobedo', 'academico.escobedo@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.escobedo@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'Escobedo', TRUE, TRUE),

  ('Dirección Plantel Pesquería', 'direccion.pesqueria@colegiomilitarizadonl.com', 'Director Plantel Pesquería', 'plantel.pesqueria@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'Pesquería', TRUE, TRUE),
  ('Coordinación Administrativa Plantel Pesquería', 'administracion.pesqueria@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.pesqueria@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'Pesquería', TRUE, TRUE),
  ('Coordinación Académica Plantel Pesquería', 'academico.pesqueria@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.pesqueria@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'Pesquería', TRUE, TRUE),

  ('Dirección Plantel Juárez', 'direccion.juarez@colegiomilitarizadonl.com', 'Director Plantel Juárez', 'plantel.juarez@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'Juárez', TRUE, TRUE),
  ('Coordinación Administrativa Plantel Juárez', 'administracion.juarez@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.juarez@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'Juárez', TRUE, TRUE),
  ('Coordinación Académica Plantel Juárez', 'academico.juarez@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.juarez@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'Juárez', TRUE, TRUE),

  ('Dirección Plantel Linares', 'direccion.linares@colegiomilitarizadonl.com', 'Director Plantel Linares', 'plantel.linares@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'Linares', TRUE, TRUE),
  ('Coordinación Administrativa Plantel Linares', 'administracion.linares@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.linares@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'Linares', TRUE, TRUE),
  ('Coordinación Académica Plantel Linares', 'academico.linares@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.linares@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'Linares', TRUE, TRUE),

  ('Dirección Plantel Galeana', 'direccion.galeana@colegiomilitarizadonl.com', 'Director Plantel Galeana', 'plantel.galeana@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'Galeana', TRUE, TRUE),
  ('Coordinación Administrativa Plantel Galeana', 'administracion.galeana@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.galeana@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'Galeana', TRUE, TRUE),
  ('Coordinación Académica Plantel Galeana', 'academico.galeana@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.galeana@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'Galeana', TRUE, TRUE),

  ('Dirección Plantel Sabinas Hidalgo', 'direccion.sabinashidalgo@colegiomilitarizadonl.com', 'Director Plantel Sabinas Hidalgo', 'plantel.sabinashidalgo@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'director', 'Sabinas Hidalgo', TRUE, TRUE),
  ('Coordinación Administrativa Plantel Sabinas Hidalgo', 'administracion.sabinashidalgo@colegiomilitarizadonl.com', 'Coordinador Administrativo', 'administracion.sabinashidalgo@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'administrative_coordination', 'Sabinas Hidalgo', TRUE, TRUE),
  ('Coordinación Académica Plantel Sabinas Hidalgo', 'academico.sabinashidalgo@colegiomilitarizadonl.com', 'Coordinador Académico', 'academica.sabinashidalgo@', crypt('CMNL2026!Temp#', gen_salt('bf')), 'academic_coordination', 'Sabinas Hidalgo', TRUE, TRUE)
ON CONFLICT (email) DO NOTHING;
```

## 5. Consultar usuarios cargados

```sql
SELECT id, email, role, campus, must_change_password, is_active
FROM colegio_militarizado_users
ORDER BY email;
```

## 6. Verificar total cargado

```sql
SELECT COUNT(*) AS total_usuarios
FROM colegio_militarizado_users;
```

## 7. Activar cambio de contraseña obligatorio

Si quieres volver a forzar que todos cambien su contraseña:

```sql
UPDATE colegio_militarizado_users
SET must_change_password = TRUE;
```

## 8. Desactivar o reactivar un usuario

```sql
UPDATE colegio_militarizado_users
SET is_active = FALSE
WHERE email = 'recepcion@colegiomilitarizadonl.com';
```

```sql
UPDATE colegio_militarizado_users
SET is_active = TRUE
WHERE email = 'recepcion@colegiomilitarizadonl.com';
```

## 9. Cambiar contraseña de un usuario

```sql
UPDATE colegio_militarizado_users
SET
  password_hash = crypt('NuevaPasswordSegura123!', gen_salt('bf')),
  must_change_password = FALSE,
  updated_at = NOW()
WHERE email = 'recepcion@colegiomilitarizadonl.com';
```

## 10. Nota de seguridad

`CORREOS.MD` contiene contraseñas iniciales en texto plano. Eso debe considerarse temporal.

Recomendado:
- mover ese archivo fuera del repo
- rotar contraseñas iniciales después de la carga
- usar solo hashes dentro de la base

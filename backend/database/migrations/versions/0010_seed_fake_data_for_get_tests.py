"""
Seed fake user, mailboxes, accounts, and email_metadata for GET endpoint testing.

All inserted records are clearly marked as 'inventadoParaEndpointGet' and are not
linked to any real provider authentication.  The fixed UUIDs make assertions trivial.
"""

from __future__ import annotations

from alembic import op


revision = "0010_seed_fake_data_for_get_tests"
down_revision = "0009_add_email_address_to_accounts"
branch_labels = None
depends_on = None

_USER_ID = "11111111-1111-4000-a000-111111111111"

_GMAIL_MAILBOX_ID = "aaaaaaaa-aaaa-4000-a000-aaaaaaaaa001"
_OUTLOOK_MAILBOX_ID = "aaaaaaaa-aaaa-4000-a000-aaaaaaaaa002"

_GMAIL_ACCOUNT_ID = "bbbbbbbb-bbbb-4000-a000-bbbbbbbbb001"
_OUTLOOK_ACCOUNT_ID = "bbbbbbbb-bbbb-4000-a000-bbbbbbbbb002"


def upgrade() -> None:
    # -- User --
    op.execute(
        f"""
        INSERT INTO users (user_id, google_sub, email, name)
        VALUES (
            '{_USER_ID}',
            'inventadoParaEndpointGet-google-sub',
            'inventadoParaEndpointGet@fake.test',
            'inventadoParaEndpointGet'
        )
        ON CONFLICT (google_sub) DO NOTHING
        """
    )

    # -- Mailboxes --
    op.execute(
        f"""
        INSERT INTO mailboxes (mailbox_id, display_name, owner_user_id)
        VALUES
            ('{_GMAIL_MAILBOX_ID}',   'Gmail inventada',   '{_USER_ID}'),
            ('{_OUTLOOK_MAILBOX_ID}', 'Outlook inventada', '{_USER_ID}')
        ON CONFLICT (mailbox_id) DO NOTHING
        """
    )

    # -- Accounts --
    op.execute(
        f"""
        INSERT INTO accounts (account_id, mailbox_id, provider, display_label, email_address)
        VALUES
            ('{_GMAIL_ACCOUNT_ID}',   '{_GMAIL_MAILBOX_ID}',   'gmail',   'Gmail inventada - inventadoParaEndpointGet',   'gmailinventada@gmail.com'),
            ('{_OUTLOOK_ACCOUNT_ID}', '{_OUTLOOK_MAILBOX_ID}', 'outlook', 'Outlook inventada - inventadoParaEndpointGet', 'outlookinventada@outlook.com')
        ON CONFLICT (account_id) DO NOTHING
        """
    )

    # -- Email metadata (Gmail: 30 ALL_MAIL + 10 SENT + 4 TRASH + 6 SPAM = 50) --
    op.execute(
        f"""
        INSERT INTO email_metadata (provider_message_id, account_id, thread_id, from_email, from_name, subject, received_at, is_read, box, previous_box)
        VALUES
            ('gmail-allmail-001', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-001', 'alice@example.com',    'Alice Johnson',    'Reunión de proyecto mañana',              '2026-03-01T09:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-002', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-001', 'bob@example.com',      'Bob Martinez',     'Re: Reunión de proyecto mañana',           '2026-03-01T09:30:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-003', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-002', 'carol@startup.io',     'Carol Chen',       'Propuesta de colaboración',                '2026-03-02T08:15:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-004', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-003', 'dave@corp.com',        'Dave Wilson',      'Actualización del presupuesto Q1',         '2026-03-02T14:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-005', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-003', 'eve@corp.com',         'Eve Thompson',     'Re: Actualización del presupuesto Q1',     '2026-03-02T15:20:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-006', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-004', 'frank@university.edu', 'Frank Rivera',     'Material del curso actualizado',           '2026-03-03T07:45:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-007', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-005', 'grace@design.co',      'Grace Kim',        'Revisión de mockups v3',                   '2026-03-03T11:00:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-008', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-005', 'henry@design.co',      'Henry Park',       'Re: Revisión de mockups v3',               '2026-03-03T11:45:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-009', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-006', 'irene@legal.com',      'Irene Salazar',    'Contrato pendiente de firma',              '2026-03-04T08:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-010', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-007', 'jack@devops.net',      'Jack Turner',      'Alerta: CPU al 95%% en producción',        '2026-03-04T10:30:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-011', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-007', 'jack@devops.net',      'Jack Turner',      'Re: Alerta resuelta - CPU normalizada',   '2026-03-04T12:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-012', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-008', 'karen@hr.com',         'Karen López',      'Recordatorio: evaluación de desempeño',    '2026-03-05T09:00:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-013', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-009', 'leo@finance.org',      'Leo Nakamura',     'Factura #4521 adjunta',                    '2026-03-05T13:15:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-014', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-010', 'mia@marketing.com',    'Mia Santos',       'Campaña de lanzamiento - borrador',        '2026-03-06T08:30:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-015', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-010', 'noah@marketing.com',   'Noah Gupta',       'Re: Campaña de lanzamiento - aprobado',    '2026-03-06T10:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-016', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-011', 'olivia@support.io',    'Olivia Brown',     'Ticket #8832 - Error en dashboard',       '2026-03-07T07:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-017', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-012', 'paul@research.edu',    'Paul Anderson',    'Resultados del estudio preliminar',        '2026-03-07T14:45:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-018', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-013', 'quinn@sales.com',      'Quinn Roberts',    'Nuevo cliente potencial - Tech Solutions', '2026-03-08T09:30:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-019', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-014', 'rachel@pm.com',        'Rachel Davis',     'Sprint planning - semana 12',              '2026-03-08T15:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-020', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-014', 'sam@pm.com',           'Sam Mitchell',     'Re: Sprint planning - tareas asignadas',   '2026-03-09T08:00:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-021', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-015', 'tina@analytics.com',   'Tina Fernández',   'Informe mensual de métricas',              '2026-03-09T11:20:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-022', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-016', 'ulises@infra.net',     'Ulises Vega',      'Migración a Kubernetes programada',        '2026-03-10T07:30:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-023', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-017', 'vera@qa.com',          'Vera White',       'Regresión detectada en módulo de pagos',   '2026-03-10T13:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-024', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-017', 'will@qa.com',          'Will Scott',       'Re: Regresión corregida - hotfix v2.1.3',  '2026-03-10T16:30:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-025', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-018', 'xena@partners.com',    'Xena Morales',     'Acuerdo de partnership - revisión legal',  '2026-03-11T08:45:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-026', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-019', 'yuri@backend.dev',     'Yuri Tanaka',      'PR #342 lista para review',                '2026-03-11T14:10:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-027', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-020', 'zoe@ux.design',        'Zoe Ellis',        'Prototipo interactivo compartido',         '2026-03-12T09:00:00Z', FALSE, 'ALL_MAIL', NULL),
            ('gmail-allmail-028', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-021', 'adam@security.io',     'Adam Blake',       'Auditoría de seguridad completada',        '2026-03-12T15:30:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-029', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-022', 'bella@data.org',       'Bella Chang',      'Dataset actualizado en S3',                '2026-03-13T08:20:00Z', TRUE,  'ALL_MAIL', NULL),
            ('gmail-allmail-030', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-023', 'carlos@mobile.dev',    'Carlos Herrera',   'Build de iOS fallido - investigando',      '2026-03-13T12:00:00Z', FALSE, 'ALL_MAIL', NULL),

            ('gmail-sent-001', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-001', 'gmailinventada@gmail.com', 'inventadoParaEndpointGet', 'Re: Reunión de proyecto mañana - confirmado',    '2026-03-01T10:00:00Z', TRUE, 'SENT', NULL),
            ('gmail-sent-002', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-003', 'gmailinventada@gmail.com', 'inventadoParaEndpointGet', 'Re: Presupuesto Q1 - aprobado',                  '2026-03-02T16:00:00Z', TRUE, 'SENT', NULL),
            ('gmail-sent-003', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-006', 'gmailinventada@gmail.com', 'inventadoParaEndpointGet', 'Re: Contrato - firmado y adjunto',               '2026-03-04T09:30:00Z', TRUE, 'SENT', NULL),
            ('gmail-sent-004', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-024', 'gmailinventada@gmail.com', 'inventadoParaEndpointGet', 'Solicitud de acceso a repositorio',              '2026-03-05T10:00:00Z', TRUE, 'SENT', NULL),
            ('gmail-sent-005', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-025', 'gmailinventada@gmail.com', 'inventadoParaEndpointGet', 'Invitación a demo del producto',                 '2026-03-06T11:00:00Z', TRUE, 'SENT', NULL),
            ('gmail-sent-006', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-011', 'gmailinventada@gmail.com', 'inventadoParaEndpointGet', 'Re: Ticket #8832 - más detalles adjuntos',       '2026-03-07T08:00:00Z', TRUE, 'SENT', NULL),
            ('gmail-sent-007', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-026', 'gmailinventada@gmail.com', 'inventadoParaEndpointGet', 'Propuesta técnica para migración',               '2026-03-08T14:00:00Z', TRUE, 'SENT', NULL),
            ('gmail-sent-008', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-015', 'gmailinventada@gmail.com', 'inventadoParaEndpointGet', 'Re: Métricas - solicitud de desglose',           '2026-03-09T12:00:00Z', TRUE, 'SENT', NULL),
            ('gmail-sent-009', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-019', 'gmailinventada@gmail.com', 'inventadoParaEndpointGet', 'Re: PR #342 - cambios solicitados',              '2026-03-11T15:00:00Z', TRUE, 'SENT', NULL),
            ('gmail-sent-010', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-022', 'gmailinventada@gmail.com', 'inventadoParaEndpointGet', 'Re: Dataset - consulta sobre formato',           '2026-03-13T09:00:00Z', TRUE, 'SENT', NULL),

            ('gmail-trash-001', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-027', 'spam-legit@promos.com',     'Promos Weekly',          'Oferta exclusiva solo hoy',                    '2026-03-02T06:00:00Z', TRUE,  'TRASH', 'ALL_MAIL'),
            ('gmail-trash-002', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-028', 'newsletter@oldservice.com', 'Old Service Newsletter', 'Tu resumen semanal - semana 9',                '2026-03-04T06:30:00Z', FALSE, 'TRASH', 'ALL_MAIL'),
            ('gmail-trash-003', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-029', 'noreply@social.com',        'Social Network',         'Alguien te mencionó en un comentario',         '2026-03-06T07:00:00Z', TRUE,  'TRASH', 'ALL_MAIL'),
            ('gmail-trash-004', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-030', 'alerts@shopping.com',       'Shopping Alerts',        'Precio rebajado en tu lista de deseos',        '2026-03-09T06:45:00Z', FALSE, 'TRASH', 'ALL_MAIL'),

            ('gmail-spam-001', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-031', 'winner@lottery-fake.com', 'Lottery Winner',        'Has ganado 1,000,000 USD',                     '2026-03-01T05:00:00Z', FALSE, 'SPAM', NULL),
            ('gmail-spam-002', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-032', 'prince@scam.ng',          'Nigerian Prince',       'Urgent business proposal',                     '2026-03-03T04:30:00Z', FALSE, 'SPAM', NULL),
            ('gmail-spam-003', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-033', 'free@crypto-scam.xyz',    'Free Crypto',           'Claim your free Bitcoin now',                  '2026-03-05T03:00:00Z', FALSE, 'SPAM', NULL),
            ('gmail-spam-004', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-034', 'admin@phishing-bank.com', 'Your Bank Security',    'Verify your account immediately',              '2026-03-07T02:15:00Z', FALSE, 'SPAM', NULL),
            ('gmail-spam-005', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-035', 'deals@cheap-meds.ru',     'Pharmacy Deals',        '70 pct off all medications - limited time',    '2026-03-09T01:00:00Z', FALSE, 'SPAM', NULL),
            ('gmail-spam-006', '{_GMAIL_ACCOUNT_ID}', 'thread-gm-036', 'support@fake-apple.com',  'Apple Support (fake)',   'Your Apple ID has been compromised',           '2026-03-11T00:30:00Z', FALSE, 'SPAM', NULL)
        ON CONFLICT (provider_message_id, account_id) DO NOTHING
        """
    )

    # -- Email metadata (Outlook: 30 ALL_MAIL + 10 SENT + 4 TRASH + 6 SPAM = 50) --
    op.execute(
        f"""
        INSERT INTO email_metadata (provider_message_id, account_id, thread_id, from_email, from_name, subject, received_at, is_read, box, previous_box)
        VALUES
            ('outlook-allmail-001', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-001', 'diana@corporate.com',     'Diana Foster',      'Agenda del comité directivo',                '2026-03-01T08:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-002', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-001', 'ethan@corporate.com',     'Ethan Hayes',       'Re: Agenda del comité directivo',            '2026-03-01T08:45:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-003', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-002', 'fiona@consulting.com',    'Fiona Grant',       'Entrega del informe de auditoría',           '2026-03-02T09:00:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-004', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-003', 'george@logistics.com',    'George Patel',      'Retraso en envío lote #7890',                '2026-03-02T13:30:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-005', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-003', 'hannah@logistics.com',    'Hannah Reed',       'Re: Retraso resuelto - envío reprogramado',  '2026-03-02T17:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-006', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-004', 'ivan@training.com',       'Ivan Kozlov',       'Certificación AWS - fecha de examen',        '2026-03-03T08:15:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-007', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-005', 'julia@product.com',       'Julia Mason',       'Roadmap Q2 - borrador para revisión',        '2026-03-03T11:30:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-008', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-005', 'kevin@product.com',       'Kevin Walsh',       'Re: Roadmap Q2 - comentarios añadidos',      '2026-03-03T14:00:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-009', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-006', 'laura@compliance.com',    'Laura Bennett',     'GDPR - actualización de política requerida', '2026-03-04T07:45:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-010', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-007', 'marcus@engineering.com',  'Marcus Young',      'Incidencia en API gateway - postmortem',     '2026-03-04T12:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-011', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-007', 'nina@engineering.com',    'Nina Ortiz',        'Re: Postmortem - action items asignados',    '2026-03-04T15:30:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-012', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-008', 'oscar@procurement.com',   'Oscar Rivera',      'Orden de compra #12345 aprobada',            '2026-03-05T09:15:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-013', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-009', 'patricia@events.com',     'Patricia Hughes',   'Conferencia Tech Summit - confirmación',     '2026-03-05T14:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-014', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-010', 'roberto@platform.io',     'Roberto Duarte',    'Release v3.5.0 - notas de versión',          '2026-03-06T08:00:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-015', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-010', 'sandra@platform.io',      'Sandra Kim',        'Re: Release v3.5.0 - deploy exitoso',        '2026-03-06T11:30:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-016', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-011', 'tomas@architecture.com',  'Tomás Vargas',      'RFC: migración a microservicios',            '2026-03-07T07:30:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-017', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-012', 'ursula@testing.com',      'Ursula Weber',      'Cobertura de tests al 92 pct - informe',     '2026-03-07T15:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-018', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-013', 'victor@cloud.com',        'Victor Nilsson',    'Factura AWS marzo - 4230 USD',               '2026-03-08T09:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-019', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-014', 'wendy@design.com',        'Wendy Torres',      'Design system v2 - componentes listos',      '2026-03-08T14:45:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-020', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-014', 'xavier@design.com',       'Xavier Luna',       'Re: Design system v2 - feedback',            '2026-03-09T08:30:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-021', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-015', 'yolanda@support.com',     'Yolanda Brooks',    'Escalación cliente VIP - prioridad alta',    '2026-03-09T11:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-022', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-016', 'zach@devrel.com',         'Zach Cooper',       'Hackathon interno - inscripciones abiertas', '2026-03-10T07:15:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-023', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-017', 'alicia@strategy.com',     'Alicia Morgan',     'Análisis competitivo Q1 - presentación',     '2026-03-10T13:30:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-024', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-017', 'bruno@strategy.com',      'Bruno Castillo',    'Re: Análisis competitivo - datos extra',     '2026-03-10T16:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-025', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-018', 'cecilia@onboarding.com',  'Cecilia Adams',     'Nuevo empleado - setup de accesos',          '2026-03-11T08:00:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-026', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-019', 'derek@database.com',      'Derek O Brien',     'Optimización de queries - resultados',       '2026-03-11T14:30:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-027', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-020', 'elena@frontend.dev',      'Elena Sato',        'Lighthouse score mejorado a 98',             '2026-03-12T08:45:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-028', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-021', 'fabian@monitoring.io',    'Fabián Cruz',       'Alerta: latencia alta en endpoint /api/v2',  '2026-03-12T15:00:00Z', FALSE, 'ALL_MAIL', NULL),
            ('outlook-allmail-029', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-022', 'gabriela@legal.com',      'Gabriela Stone',    'NDA firmado - copia adjunta',                '2026-03-13T08:00:00Z', TRUE,  'ALL_MAIL', NULL),
            ('outlook-allmail-030', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-023', 'hector@cicd.io',          'Héctor Romero',     'Pipeline CI roto en rama develop',           '2026-03-13T12:30:00Z', FALSE, 'ALL_MAIL', NULL),

            ('outlook-sent-001', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-001', 'outlookinventada@outlook.com', 'inventadoParaEndpointGet', 'Re: Agenda del comité - puntos añadidos',        '2026-03-01T09:00:00Z', TRUE, 'SENT', NULL),
            ('outlook-sent-002', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-003', 'outlookinventada@outlook.com', 'inventadoParaEndpointGet', 'Re: Envío - solicitud de tracking',              '2026-03-02T18:00:00Z', TRUE, 'SENT', NULL),
            ('outlook-sent-003', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-006', 'outlookinventada@outlook.com', 'inventadoParaEndpointGet', 'Re: GDPR - política actualizada adjunta',        '2026-03-04T09:00:00Z', TRUE, 'SENT', NULL),
            ('outlook-sent-004', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-024', 'outlookinventada@outlook.com', 'inventadoParaEndpointGet', 'Solicitud de presupuesto para herramientas',     '2026-03-05T10:30:00Z', TRUE, 'SENT', NULL),
            ('outlook-sent-005', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-025', 'outlookinventada@outlook.com', 'inventadoParaEndpointGet', 'Reporte semanal de progreso - semana 10',        '2026-03-06T12:00:00Z', TRUE, 'SENT', NULL),
            ('outlook-sent-006', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-011', 'outlookinventada@outlook.com', 'inventadoParaEndpointGet', 'Re: RFC microservicios - comentarios',           '2026-03-07T09:00:00Z', TRUE, 'SENT', NULL),
            ('outlook-sent-007', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-026', 'outlookinventada@outlook.com', 'inventadoParaEndpointGet', 'Documentación de API actualizada',               '2026-03-08T15:00:00Z', TRUE, 'SENT', NULL),
            ('outlook-sent-008', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-015', 'outlookinventada@outlook.com', 'inventadoParaEndpointGet', 'Re: Escalación VIP - seguimiento realizado',     '2026-03-09T12:30:00Z', TRUE, 'SENT', NULL),
            ('outlook-sent-009', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-019', 'outlookinventada@outlook.com', 'inventadoParaEndpointGet', 'Re: Queries optimizadas - aprobado para prod',   '2026-03-11T15:30:00Z', TRUE, 'SENT', NULL),
            ('outlook-sent-010', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-022', 'outlookinventada@outlook.com', 'inventadoParaEndpointGet', 'Re: NDA - confirmación de recepción',            '2026-03-13T09:00:00Z', TRUE, 'SENT', NULL),

            ('outlook-trash-001', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-027', 'events@webinar-spam.com',  'Webinar Invites',        'Webinar gratuito: cómo ganar dinero rápido',   '2026-03-02T05:30:00Z', TRUE,  'TRASH', 'ALL_MAIL'),
            ('outlook-trash-002', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-028', 'digest@oldplatform.com',   'Old Platform Digest',    'Tu actividad de la semana en OldPlatform',     '2026-03-04T06:00:00Z', FALSE, 'TRASH', 'ALL_MAIL'),
            ('outlook-trash-003', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-029', 'noreply@forum.old',        'Old Forum',              'Nuevo post en hilo que sigues',                '2026-03-06T07:30:00Z', TRUE,  'TRASH', 'ALL_MAIL'),
            ('outlook-trash-004', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-030', 'promo@deals-daily.com',    'Daily Deals',            'Flash sale - últimas 2 horas',                 '2026-03-09T06:00:00Z', FALSE, 'TRASH', 'ALL_MAIL'),

            ('outlook-spam-001', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-031', 'ceo@fake-company.biz',     'Fake CEO',                  'Wire transfer needed urgently',                '2026-03-01T04:00:00Z', FALSE, 'SPAM', NULL),
            ('outlook-spam-002', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-032', 'helpdesk@phish-it.com',    'IT Helpdesk (fake)',         'Password reset required - click here',         '2026-03-03T03:30:00Z', FALSE, 'SPAM', NULL),
            ('outlook-spam-003', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-033', 'invest@ponzi-scheme.xyz',  'Investment Guru',            '300 pct returns guaranteed - act now',          '2026-03-05T02:00:00Z', FALSE, 'SPAM', NULL),
            ('outlook-spam-004', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-034', 'survey@gift-card-scam.com','Free Gift Cards',            'Complete survey for 500 USD Amazon gift card',  '2026-03-07T01:15:00Z', FALSE, 'SPAM', NULL),
            ('outlook-spam-005', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-035', 'pills@miracle-health.ru',  'Miracle Health',             'Lose 20kg in 1 week - doctors hate this',      '2026-03-09T00:45:00Z', FALSE, 'SPAM', NULL),
            ('outlook-spam-006', '{_OUTLOOK_ACCOUNT_ID}', 'thread-ol-036', 'microsoft@fake-ms.com',    'Microsoft Security (fake)',  'Your Office 365 license will expire today',    '2026-03-11T00:00:00Z', FALSE, 'SPAM', NULL)
        ON CONFLICT (provider_message_id, account_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM email_metadata WHERE account_id IN ('{_GMAIL_ACCOUNT_ID}', '{_OUTLOOK_ACCOUNT_ID}')"
    )
    op.execute(
        f"DELETE FROM accounts WHERE account_id IN ('{_GMAIL_ACCOUNT_ID}', '{_OUTLOOK_ACCOUNT_ID}')"
    )
    op.execute(
        f"DELETE FROM mailboxes WHERE mailbox_id IN ('{_GMAIL_MAILBOX_ID}', '{_OUTLOOK_MAILBOX_ID}')"
    )
    op.execute(
        f"DELETE FROM users WHERE user_id = '{_USER_ID}'"
    )

// =====================================================================
// Bootstrap-индексы MongoDB для дипломного проекта.
// Запускается один раз при пустом volume mongo (через docker-entrypoint
// /docker-entrypoint-initdb.d). Источник: docs/design/databases/mongo.md.
// =====================================================================

const dbName = process.env.MONGO_INITDB_DATABASE || 'diploma';
const target = db.getSiblingDB(dbName);

// ----- messages -----
target.createCollection('messages');
target.messages.createIndex({ source_id: 1, external_id: 1 }, { unique: true, name: 'ux_messages_source_external' });
target.messages.createIndex({ published_at: -1 }, { name: 'ix_messages_published' });
target.messages.createIndex({ channel_kind: 1, published_at: -1 }, { name: 'ix_messages_kind_published' });
target.messages.createIndex({ channel_site: 1, published_at: -1 }, { name: 'ix_messages_site_published' });

// ----- annotated_messages -----
target.createCollection('annotated_messages');
target.annotated_messages.createIndex({ message_id: 1, is_active: 1 }, { name: 'ix_annmsg_message_active' });
target.annotated_messages.createIndex({ 'topics.slug': 1, is_active: 1 }, { name: 'ix_annmsg_topic_active' });
target.annotated_messages.createIndex({ is_ad: 1, is_active: 1 }, { name: 'ix_annmsg_isad_active' });
target.annotated_messages.createIndex({ 'sentiment.label': 1, is_active: 1 }, { name: 'ix_annmsg_sentiment_active' });
target.annotated_messages.createIndex({ 'entities.district_slug': 1 }, { name: 'ix_annmsg_district' });
target.annotated_messages.createIndex({ model_run_id: 1 }, { name: 'ix_annmsg_run' });

// ----- objects -----
target.createCollection('objects');
target.objects.createIndex({ source_id: 1, external_id: 1 }, { unique: true, name: 'ux_objects_source_external' });
target.objects.createIndex({ object_kind: 1, status: 1, published_at: -1 }, { name: 'ix_objects_kind_status_published' });
target.objects.createIndex({ channel_site: 1, published_at: -1 }, { name: 'ix_objects_site_published' });
target.objects.createIndex({ 'listing.address.district_slug': 1, status: 1 }, { name: 'ix_objects_district_status' });
target.objects.createIndex({ published_at: -1 }, { name: 'ix_objects_published' });
target.objects.createIndex({ 'listing.address.lat': 1, 'listing.address.lon': 1 }, { name: 'ix_objects_geo' });

// ----- annotated_objects -----
target.createCollection('annotated_objects');
target.annotated_objects.createIndex({ object_id: 1, is_active: 1 }, { name: 'ix_annobj_object_active' });
target.annotated_objects.createIndex({ is_active: 1, is_undervalued: 1, deviation_pct: 1 }, { name: 'ix_annobj_undervalued' });
target.annotated_objects.createIndex({ model_run_id: 1 }, { name: 'ix_annobj_run' });
target.annotated_objects.createIndex({ model_version: 1, is_active: 1 }, { name: 'ix_annobj_version_active' });
target.annotated_objects.createIndex({ rank_in_run: 1, model_run_id: 1 }, { name: 'ix_annobj_rank_run' });

print('[init] Mongo indexes created in db=' + dbName);

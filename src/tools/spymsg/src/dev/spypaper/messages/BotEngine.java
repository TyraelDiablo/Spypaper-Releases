package dev.spypaper.messages;

import com.mojang.authlib.GameProfile;
import io.netty.channel.embedded.EmbeddedChannel;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import net.minecraft.network.Connection;
import net.minecraft.network.protocol.Packet;
import net.minecraft.network.protocol.PacketFlow;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ClientInformation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.CommonListenerCookie;
import net.minecraft.world.InteractionHand;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.BlockFace;
import org.bukkit.craftbukkit.CraftServer;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.craftbukkit.entity.CraftEntity;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.util.RayTraceResult;

/**
 * Spypaper bot motoru: sunucuya gerçek oyuncu gibi giren sahte oyuncular (Carpet'in fake player'ı gibi).
 * Ağ bağlantısı yoktur (boş bir Netty kanalı); oyuncu dünyaya eklenir, chunk yükler, fizik işler.
 * İşler: none (durur), attack (baktığı varlığa vurur), use (baktığı bloğa/havaya sağ tık), sneak.
 */
final class BotEngine {
    static final class Bot {
        ServerPlayer handle;
        String action = "none";
        int interval = 0;          // 0: her tick (vurmada saldırı gücü dolunca)
        int timer = 0;
    }

    /** Paketleri yutan bağlantı. */
    static final class FakeConnection extends Connection {
        FakeConnection() {
            super(PacketFlow.SERVERBOUND);
            this.channel = new EmbeddedChannel();
            this.address = new InetSocketAddress("127.0.0.1", 0);
        }

        @Override
        public void send(Packet<?> packet, io.netty.channel.ChannelFutureListener l, boolean flush) {
        }

        @Override
        public boolean isConnected() {
            return true;
        }
    }

    private final JavaPlugin plugin;
    final Map<String, Bot> bots = new LinkedHashMap<>();

    BotEngine(JavaPlugin plugin) {
        this.plugin = plugin;
        Bukkit.getScheduler().runTaskTimer(plugin, this::tick, 1L, 1L);
    }

    static UUID offlineUuid(String name) {
        return UUID.nameUUIDFromBytes(("OfflinePlayer:" + name).getBytes(StandardCharsets.UTF_8));
    }

    String spawn(String name, World world, double x, double y, double z, float yaw, float pitch) {
        if (bots.containsKey(name.toLowerCase())) remove(name);
        Player existing = Bukkit.getPlayerExact(name);
        if (existing != null) return "busy";
        MinecraftServer server = ((CraftServer) Bukkit.getServer()).getServer();
        ServerLevel level = ((CraftWorld) world).getHandle();
        GameProfile profile = new GameProfile(offlineUuid(name), name);
        ServerPlayer p = new ServerPlayer(server, level, profile, ClientInformation.createDefault());
        FakeConnection conn = new FakeConnection();
        server.getPlayerList().placeNewPlayer(conn, p, CommonListenerCookie.createInitial(profile, false));
        Bot b = new Bot();
        b.handle = p;
        bots.put(name.toLowerCase(), b);
        p.getBukkitEntity().teleport(new Location(world, x, y, z, yaw, pitch));
        return "ok";
    }

    void remove(String name) {
        Bot b = bots.remove(name.toLowerCase());
        if (b == null) return;
        MinecraftServer server = ((CraftServer) Bukkit.getServer()).getServer();
        String shown = b.handle.getGameProfile().name();
        server.getPlayerList().remove(b.handle);
        Bukkit.getLogger().info(shown + " left the game");   // panel/log izleyicileri çıkışı görsün
    }

    void removeAll() {
        for (String n : bots.keySet().toArray(new String[0])) remove(n);
    }

    boolean setAction(String name, String action, int interval) {
        Bot b = bots.get(name.toLowerCase());
        if (b == null) return false;
        b.action = action;
        b.interval = Math.max(0, interval);
        b.timer = 0;
        b.handle.getBukkitEntity().setSneaking("sneak".equals(action));
        return true;
    }

    private void tick() {
        for (Bot b : bots.values().toArray(new Bot[0])) {
            ServerPlayer p = b.handle;
            if (p.isRemoved()) {
                bots.values().remove(b);
                continue;
            }
            try {
                p.doTick();                      // gerçek oyuncuda bunu bağlantı çağırır: fizik, yer çekimi
            } catch (Throwable ignored) {
            }
            if (!p.isAlive()) continue;
            if ("attack".equals(b.action)) {
                boolean ready = b.interval > 0 ? ++b.timer >= b.interval : p.getAttackStrengthScale(0.5f) >= 1.0f;
                if (ready) {
                    b.timer = 0;
                    attack(p);
                }
            } else if ("use".equals(b.action)) {
                if (++b.timer >= Math.max(1, b.interval)) {
                    b.timer = 0;
                    use(p);
                }
            }
        }
    }

    private void attack(ServerPlayer p) {
        Player bp = p.getBukkitEntity();
        Entity target = bp.getTargetEntity(3);
        if (target != null) {
            p.attack(((CraftEntity) target).getHandle());
        }
        p.getBukkitEntity().swingMainHand();
        p.resetAttackStrengthTicker();
    }

    private void use(ServerPlayer p) {
        Player bp = p.getBukkitEntity();
        RayTraceResult hit = bp.rayTraceBlocks(4.5);
        if (hit != null && hit.getHitBlock() != null && hit.getHitBlockFace() != null) {
            Block blk = hit.getHitBlock();
            BlockFace f = hit.getHitBlockFace();
            Vec3 pos = new Vec3(hit.getHitPosition().getX(), hit.getHitPosition().getY(), hit.getHitPosition().getZ());
            BlockHitResult bhr = new BlockHitResult(pos, Direction.valueOf(f.name()),
                    new BlockPos(blk.getX(), blk.getY(), blk.getZ()), false);
            if (p.gameMode.useItemOn(p, p.level(), p.getItemInHand(InteractionHand.MAIN_HAND), InteractionHand.MAIN_HAND, bhr)
                    .consumesAction()) {
                p.getBukkitEntity().swingMainHand();
                return;
            }
        }
        p.gameMode.useItem(p, p.level(), p.getItemInHand(InteractionHand.MAIN_HAND), InteractionHand.MAIN_HAND);
        p.getBukkitEntity().swingMainHand();
    }
}

package dev.spypaper.nodeeplava;

import java.util.Random;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.world.WorldInitEvent;
import org.bukkit.generator.BlockPopulator;
import org.bukkit.generator.LimitedRegion;
import org.bukkit.generator.WorldInfo;
import org.bukkit.plugin.java.JavaPlugin;

/** Spypaper: derin mağaralardaki lavı (Y -55 ve altı, tabanın 10 blok üstüne kadar) yeni chunk'larda havaya çevirir. */
public final class NoDeepLava extends JavaPlugin implements Listener {
    static final int LAVA_TOP = -55;      // oyunun mağara lavı Y -54'ün altında başlar
    static final int FLOOR_KEEP = 10;     // tabana bu kadar yakın lav olduğu gibi kalır

    static final class Populator extends BlockPopulator {
        @Override
        public void populate(WorldInfo info, Random random, int cx, int cz, LimitedRegion region) {
            int low = info.getMinHeight() + FLOOR_KEEP;
            if (low > LAVA_TOP) return;
            int bx = cx << 4, bz = cz << 4;
            for (int x = bx; x < bx + 16; x++)
                for (int z = bz; z < bz + 16; z++)
                    for (int y = low; y <= LAVA_TOP; y++)
                        if (region.getType(x, y, z) == Material.LAVA) region.setType(x, y, z, Material.AIR);
        }
    }

    private final Populator populator = new Populator();

    private void attach(World w) {
        if (!w.getPopulators().contains(populator)) w.getPopulators().add(populator);
    }

    @Override
    public void onEnable() {
        for (World w : getServer().getWorlds()) attach(w);
        getServer().getPluginManager().registerEvents(this, this);
    }

    @EventHandler
    public void onWorldInit(WorldInitEvent e) { attach(e.getWorld()); }
}
